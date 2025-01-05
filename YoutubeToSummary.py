import os
import re
import unicodedata
import time

from tqdm import tqdm
from openai import OpenAI
from youtube_transcript_api import YouTubeTranscriptApi


def get_video_id(youtube_url):
    """
    Extract video ID from YouTube URL.
    It handles patterns like youtube.com/watch?v=VIDEO_ID or youtu.be/VIDEO_ID
    """
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/)([A-Za-z0-9_-]+)',
        r'youtube\.com/embed/([A-Za-z0-9_-]+)'
    ]

    for pattern in patterns:
        match = re.search(pattern, youtube_url)
        if match:
            return match.group(1)
    raise ValueError("Invalid YouTube URL")


def get_transcript(video_id):
    """
    Get transcript from YouTube video.
    By default, it always picks manually created transcripts over automatically created ones.
    """
    try:
        return YouTubeTranscriptApi.get_transcript(video_id)
    except Exception as e:
        raise Exception(f"Error fetching transcript for {video_id}: {str(e)}")


def clean_transcript_text(transcript_list):
    """Clean and format transcript text with proper sentence breaks."""

    def clean_fragment(text):
        """Clean individual text fragments."""

        # Normalize Unicode characters
        text = unicodedata.normalize('NFKD', text)

        # Remove non-breaking spaces and similar artifacts
        text = re.sub(r'\[\s*_+\s*\]', '', text)  # Remove [___] patterns
        text = re.sub(r'\xa0', ' ', text)  # Replace non-breaking spaces
        text = re.sub(r'\u200b', '', text)  # Remove zero-width spaces
        text = re.sub(r'\s+', ' ', text)  # Normalize all whitespace

        return text.strip()

    # First pass: join text fragments into a single string
    full_text = ""

    for i, entry in enumerate(transcript_list):
        current_text = clean_fragment(entry['text'])

        # Skip empty entries
        if not current_text:
            continue

        # Check if this fragment ends with sentence-ending punctuation
        ends_with_punct = current_text[-1] in '.!?'

        # Add the current text
        full_text += current_text

        # If this doesn't end with punctuation, check if we should add a space
        if not ends_with_punct and i < len(transcript_list) - 1:
            next_text = clean_fragment(transcript_list[i + 1]['text'])
            # Add space if the next fragment doesn't start with punctuation
            if next_text and not next_text[0] in '.,!?':
                full_text += ' '

    # Clean up common transcript issues
    cleaned_text = (
        full_text
        # Remove multiple spaces
        .replace('  ', ' ')
        # Add space after period if missing
        .replace('.', '. ')
        .replace('.  ', '. ')
        # Add space after comma if missing
        .replace(',', ', ')
        .replace(',  ', ', ')
        # Remove spaces before punctuation
        .replace(' .', '.')
        .replace(' ,', ',')
        .replace(' !', '!')
        .replace(' ?', '?')
        # Fix common transcript artifacts
        .replace('[Music]', '')
        .replace('[Applause]', '')
        .replace('[Laughter]', '')
    )

    # Remove speaker labels and timestamps using regex
    cleaned_text = re.sub(r'\[?Speaker \d+\]?:\s*', '', cleaned_text)
    cleaned_text = re.sub(r'\[\d{2}:\d{2}:\d{2}\]', '', cleaned_text)

    # Split into sentences and rejoin with proper spacing
    sentences = re.split(r'(?<=[.!?])\s+', cleaned_text)
    formatted_text = ' '.join(sentence.strip() for sentence in sentences if sentence.strip())

    return formatted_text


def chunk_text(text, max_tokens=4000):
    """Split text into chunks to respect token limits."""
    words = text.split()
    chunks = []
    current_chunk = []
    current_length = 0

    for word in words:
        # Approximate token count (words * 1.3 for safety margin)
        word_tokens = len(word.split()) * 1.3
        if current_length + word_tokens > max_tokens:
            chunks.append(' '.join(current_chunk))
            current_chunk = [word]
            current_length = word_tokens
        else:
            current_chunk.append(word)
            current_length += word_tokens

    if current_chunk:
        chunks.append(' '.join(current_chunk))

    return chunks


def cleanup_chunk(client, chunk):
    """Using the LLM to directly cleanup each chunk, much better results than regex/code based cleanup."""
    try:
        cleanup_response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """You are an expert at cleaning up raw podcast transcripts. Your tasks:
                    1. Fix sentence structure and punctuation
                    2. Remove filler words (um, uh, like, you know etc.)
                    3. Clean up false starts and repeated phrases
                    4. Maintain the original meaning and speaker's intent
                    5. Keep important verbal emphasis or emotional context
                    6. Present the text as clean, properly punctuated paragraphs

                    Only return the cleaned text, no explanations or meta-commentary."""
                },
                {
                    "role": "user",
                    "content": f"Clean up this podcast transcript section, maintaining its meaning but removing speech artifacts:\n\n{chunk}"
                }
            ],
            temperature=0.3,  # Lower temperature for more consistent cleaning
            max_tokens=1500
        )
        cleaned_chunk = cleanup_response.choices[0].message.content
    except Exception as e:
        raise Exception(f"Couldn't clean up input chunk because of {e}")

    return cleaned_chunk


def summarize_chunk(client, cleaned_chunk):
    try:
        summary_response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": f"""You are a skilled podcast summarizer:
                        1. Identify the main topics and key points
                        2. Capture important insights and arguments
                        3. Include relevant examples or cases mentioned
                        4. Maintain the logical flow of the discussion
                        5. Highlight any significant conclusions or takeaways
                        6. Ignore low stake exchanges such as background presentation of the guests etc."""
                    },
                    {
                        "role": "user",
                        "content": f"Provide a detailed summary of this podcast section:\n\n{cleaned_chunk}"
                    }
                ],
                temperature=0.7,
                max_tokens=500
            )
    except Exception as e:
        raise Exception(f"Error generating summary: {str(e)}")
    return summary_response.choices[0].message.content


if __name__ == "__main__":
    # https://platform.openai.com/
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    if not OPENAI_API_KEY:
        raise ValueError("Please set the OPENAI_API_KEY environment variable")

    youtube_url = input("Enter YouTube URL: ")

    client = OpenAI(api_key=OPENAI_API_KEY)
    video_id = get_video_id(youtube_url)
    transcript = get_transcript(video_id)
    clean_transcript = clean_transcript_text(transcript)
    chunks = chunk_text(clean_transcript)

    chunk_summaries = []
    for chunk in tqdm(chunks):
        chunk = cleanup_chunk(client, chunk)
        time.sleep(20)  # To avoid rate limits error
        summary = summarize_chunk(client, chunk)
        chunk_summaries.append(summary)
        time.sleep(5)  # To avoid rate limits error

    summary_file = f"podcast_summary_{video_id}.md"
    with open(summary_file, "w") as f:
        print(f"Summary in markdown format saved to : {summary_file}")
        # Usual chatgpt markdown format string
        final_summary = "\n\n".join([
            "# Podcast Summary",
            "## Overview",
            *chunk_summaries,
        ])
        f.write(final_summary)

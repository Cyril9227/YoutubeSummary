# YoutubeSummary
Podcast to chatgpt style bullet points markdown summary

## Usage

Install the required packages

```bash
pip install openai
pip install youtube_transcript_api
```

Set the environment variable `OPENAI_API_KEY` to your OpenAI API key (use `set` instead of `export` on Windows). Protip: new accounts get 5$ of free credits.

```bash
export OPEN_AI_API_KEY=your-api-key
```

When runnning the script, you'll be prompted to enter the youtube link you want to summarize. Final output will be saved in a markdown file in the same directory as the script.

```bash
python YoutubeToSummary.py
```

## Todo
- [ ] Add smarter errors handling for rate limits
- [ ] Web interface / app ? 
- [ ] Play with prompts to get a more concise summary
- [ ] Add more options for the output format or destination
- [ ] Cache the chunks or something to avoid reprocessing everything if interrupted or run multiple times
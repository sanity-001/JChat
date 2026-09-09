# JChat

[中文](README.md) | [English](README.en.md)

A Windows desktop AI companion with long-term memory, voice interaction, and real working skills — a chibi sprite buddy who remembers your life, listens, speaks, and helps you get things done.

> **Highlights**
> - **Chibi sprite companion**: always-on-top transparent window, 10 expressions, blinking idle, lip-sync while talking, per-part click reactions (ahoge / tail / head / body), running animation while dragged, proactive chat
> - **Voice interaction**: push-to-talk with local speech recognition (SenseVoice, offline) + spoken replies (GPT-SoVITS voice cloning / EdgeTTS fallback) + hands-free wake word + talk-to-interrupt
> - **Play together**: say "let's play Gomoku" and she opens the board, trash-talking in character every move
> - **Long-term memory** (retrieval precision × presence):
>   - **Recent-life strip** — everything that slid out of the short-term window is compressed into first-person dated summaries, always present in context
>   - **Memory cards** — facts auto-extracted every turn (with timestamps) injected by relevance
>   - **Knowledge graph** — entity-relation triples from conversations, with entity linking & graph search
>   - **Active recall** — a `recall` tool lets her look things up herself; "remember when…" auto-triggers it
>   - **Semantic retrieval** (optional) — `uv sync --extra semantic` enables local bge-small-zh embeddings (onnx, no torch); hybrid cosine + lexical scoring, auto-degrades gracefully
> - **Agent skills**: standard tool-calling loop + 12 tools (local Python / file ops / web search / screen vision / self-scheduled reminders / memory read-write)
> - **Cost-conscious**: 800-token memory card budget, priority queue, single-worker serialization

## Demo

| Interaction | Gomoku together |
|:---:|:---:|
| <img src="screenshots/demo-companion.gif" width="200"> | <img src="screenshots/demo-gomoku.gif" width="440"> |
| Click ahoge/tail/head/body for custom reactions; she runs in the direction you drag; expressions follow her work | Say "let's play Gomoku" to start; she comments on the game in character, celebrates wins and sulks at losses |

## Getting Started

```bash
uv sync --extra voice --extra semantic  # Python 3.12+, uv-managed
uv run python -m JChat
```

- Windows 10/11 (screen vision relies on win32 API)
- Any OpenAI-compatible LLM endpoint (DeepSeek recommended); put the key in `config.private.json`
- Voice: first push-to-talk downloads the SenseVoice model (~200MB, one-time). For her custom voice: run a GPT-SoVITS `api_v2` service and set the reference audio + its transcript in Settings

> ⚠️ **Disclaimer**: runs locally with **no sandbox** — `run_python` can access local files and the network. Use at your own discretion.

## Privacy

- All conversations, memories, and the knowledge graph stay in a local SQLite file
- The only data leaving your machine is what you send to the LLM endpoint you configured yourself

## Character Assets

The bundled sprite (`assets/live2d/web/sprite/pets/vivimi`) is a fan-made derivative of **Wiš'adel** from *Arknights*:

- Copyright belongs to Hypergryph and the original fan artist; personal use only, **no commercial use**
- Replace with any Petdex spritesheet (`pet.json` + 8×9 grid) by swapping the folder

## Development

```bash
uv run --with pytest pytest        # tests
uv run --with ruff ruff check src  # lint
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for architecture conventions (tool registry, input-source interface, memory pipeline stages, thread discipline).

## License

[GPL-3.0](LICENSE) © 2026 JChat authors. By using this repository you also agree to the respective licenses of the bundled fan-made assets.

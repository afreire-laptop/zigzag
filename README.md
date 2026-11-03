<p align="center">
  <img src="zigzag_logo.png" alt="zigzag logo" width="160">
</p>

<h1 align="center">zigzag</h1>

<p align="center">Turning an ambiguous brief into explicit human choices.</p>

zigzag is an AI-powered proof of concept that helps users refine their intent through deliberate choices and instructions. Assumptions and unresolved questions remain explicit, while the model proposes rather than decides. [The product tenet](docs/product/tenet.md) sets the product boundary, and [the journeys](docs/product/journeys.md) fix the expected behavior. Check [docs/README.md](docs/README.md) for additional documentation.

## Stack

- Backend API built with FastAPI and Pydantic.
- Frontend Web app, built with React and served via NGINX.
- OpenRouter for model communication.
- Docker to run the app.

[ADR 0001](docs/decisions/0001-python-api-and-workspace.md) documents the stack choices.

## Run it

```sh
cp .env.example .env
docker compose up --build
```

Then open http://127.0.0.1:8080.

The app starts in **fixture mode** by default: it serves preset journey responses for the fixture texts, labels them as fixtures everywhere, and refuses any other text.

To use another port, set it in the shell, for example `ZIGZAG_WEB_PORT=9090 docker compose up`. Do not put `ZIGZAG_WEB_PORT` in `.env`: Compose passes `.env` to the API, which refuses settings it does not know.

### Live mode

Set these three values in `.env`, then run `docker compose up` again:

```sh
ZIGZAG_MODEL_MODE=live
ZIGZAG_OPENROUTER_API_KEY=...
ZIGZAG_MODEL=provider/model-name    # an explicit OpenRouter slug for a model
```

Before you use live mode or keep projects you care about, read [Before you run it](CONTRIBUTING.md#before-you-run-it), which covers cost, data, and security.

## How it works

A model result applies only if the brief is unchanged since the work started, and a request that may have reached the model is never repeated automatically. [Model work and records](docs/reference/model-work-and-records.md) covers operations, paid requests, reloads and restarts, and how projects are stored. [The handoff format](docs/reference/handoff-format.md) describes the export.

## Contributing

[CONTRIBUTING.md](CONTRIBUTING.md) covers the toolchain, local development, configuration, the checks, and live evaluation.

## License

MIT. See [LICENSE](LICENSE).

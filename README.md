# zigzag

zigzag is a proof of concept that turns an ambiguous brief into explicit human choices and a reviewed handoff.

Intent changes only through the user's own choices and instructions. Assumptions and unresolved questions stay visible, and the model only proposes. [The product tenet](docs/product/tenet.md) sets the product boundary, and [the journeys](docs/product/journeys.md) fix the expected behavior. [docs/README.md](docs/README.md) maps the rest of the documentation.

## Stack

- Backend API built with FastAPI and Pydantic.
- Frontend Web app, built with React and served via NGINX.
- OpenRouter for model communication.
- Docker to run the app.

[ADR 0001](docs/decisions/0001-python-api-and-workspace.md) records the architecture and the reasons for it.

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

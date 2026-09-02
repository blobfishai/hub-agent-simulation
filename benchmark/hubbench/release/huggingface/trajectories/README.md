# Trajectories

`index.json` lists every trajectory. **Reference** trajectories are the durable world call traces of the packaged oracle replayed through the public surfaces (MCP over HTTP, REST, the `tool` CLI, answer submission) inside Harbor under Docker and graded by the packaged verifier — 32 published. **Model** trajectories come from imported Harbor runs of `blobfishai/hubbench` with the same durable trace, the HubScore verdict, and the token/cost receipt per trial; a run is ranked only when it completed every published task once with zero errors and zero retries, otherwise it is a disclosed partial run. Qualification controls are never ranked as models.

## Model runs

- **GPT-5.6 Luna (Codex 0.151.0, max reasoning)** — `harbor run -d blobfishai/hubbench@v1.0.0 -a codex 0.151.0 · model gpt-5.6-luna` — disclosed-partial: 5/40 tasks, mean HubScore 66.22, strict passes 0, mean cost $0.0726. Disclosed partial run: 5 of 40 published tasks (one per family). Trajectories only — never ranked.

Each trace lists every tool call the world recorded (tool, arguments, success, result — long results are truncated with a character count). Traces from v1.0.0 packages include repeated argument-free `hubbench.context.get` reads caused by the compose healthcheck polling the task endpoint; v1.1.0 packages probe the private `/health` endpoint instead.

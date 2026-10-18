set positional-arguments

# Application settings are in config.d; CLI overrides follow them.
ROOT := env_var("TOLTECA_DEPLOY_ROOT")

_default:
    @just --list

# Run the observation planner on Dash's development server.
obs_planner *ARGS:
    cd "{{ROOT}}" && uv run --project "{{ROOT}}" tolteca_simu obs_planner run --config_paths "{{SVC_DIR}}/config.d" "$@"

# Serve the observation planner with gunicorn, for production behind a proxy.
obs_planner_serve *ARGS:
    cd "{{ROOT}}" && uv run --project "{{ROOT}}" tolteca_simu obs_planner serve --config_paths "{{SVC_DIR}}/config.d" "$@"

# Inspect the resolved planner settings.
show_config *ARGS:
    cd "{{ROOT}}" && uv run --project "{{ROOT}}" tolteca_simu obs_planner show_config --config_paths "{{SVC_DIR}}/config.d" "$@"

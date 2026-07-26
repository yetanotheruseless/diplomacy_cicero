# Diplomacy Cicero Test Scripts

## IMPORTANT: Run All Tests Inside Docker Container ONLY

These scripts **MUST** be run inside the Docker container, not on the host system. Running them on the host system will fail because:

1. The protobuf files are compiled for the container's environment
2. The C++ shared libraries are built for the container's architecture
3. Dependencies are installed in the container's Python environment

## Usage Instructions

First, build and run the Docker container:

```bash
# Build the container
./scripts/docker_build.sh

# Run the container
./scripts/docker_run.sh
```

Once inside the container, run the verification scripts:

```bash
# Run basic verification
./scripts/verify_full_build.sh

# Run comprehensive verification
./scripts/verify_full_build.sh --full-test

# Run specific test scripts
python test_scripts/verify_heyhi.py
python test_scripts/verify_imports.py
python test_scripts/test_full_pipeline.py
```

## Testing the Full Agent

To run a game with a Cicero agent as Turkey against six imitation agents:

```bash
python run.py --adhoc --cfg conf/c01_ag_cmp/cmp.prototxt Iagent_one=agents/cicero.prototxt Iagent_six=agents/ablations/cicero_imitation_only.prototxt power_one=TURKEY
```

## Troubleshooting

If tests fail, check:

1. Did you run inside the Docker container?
2. Is the pydipcc module built correctly? Check with: `python test_pydipcc.py`
3. Are protobuf files compiled? Check with: `python -c "from conf import conf_pb2; print('OK')"`
4. Do you have enough memory allocated to the Docker container? Check docker-compose.yml
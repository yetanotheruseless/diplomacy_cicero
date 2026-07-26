# Docker Release Process

This repository builds two artifacts from one supported stack:

- `cpu-build` — Ubuntu 24.04 with `torch==2.13.0+cpu`
- `cuda-runtime` — Ubuntu 24.04/CUDA 13.0 with
  `torch==2.13.0+cu130`

Model weights are not embedded in either image.

## Preconditions

Before tagging a release:

1. the CPU GitHub Actions job must pass;
2. the `cuda-runtime` target must construct;
3. B5 and B1 must pass on the release commit;
4. B2/B3 must pass on a CUDA 13-compatible GPU; and
5. documentation and exact version assertions must match the Dockerfile.

Historical cu124 or earlier-protoc logs do not satisfy these gates.

## Local release candidate

Replace `<version>` with the intended immutable release tag:

```bash
docker buildx build \
  --platform linux/amd64 \
  --target cpu-build \
  --load \
  -t diplomacy-cicero:<version>-cpu .

docker run --rm diplomacy-cicero:<version>-cpu \
  ./scripts/verify_full_build.sh --accelerator cpu

docker buildx build \
  --platform linux/amd64 \
  --target cuda-runtime \
  --load \
  -t diplomacy-cicero:<version>-cu130 .
```

On a GPU host:

```bash
docker run --rm --gpus all diplomacy-cicero:<version>-cu130 \
  ./scripts/verify_full_build.sh --accelerator cuda --require-gpu
```

## Publish

Choose a registry namespace and authenticate. For GitHub Container Registry:

```bash
printf '%s' "$GITHUB_TOKEN" | \
  docker login ghcr.io -u "$GITHUB_USER" --password-stdin

docker tag \
  diplomacy-cicero:<version>-cpu \
  ghcr.io/<owner>/diplomacy-cicero:<version>-cpu
docker tag \
  diplomacy-cicero:<version>-cu130 \
  ghcr.io/<owner>/diplomacy-cicero:<version>-cu130

docker push ghcr.io/<owner>/diplomacy-cicero:<version>-cpu
docker push ghcr.io/<owner>/diplomacy-cicero:<version>-cu130
```

Record the content digests printed by the registry. Deploy by digest when
reproducibility matters.

## Release metadata

Release notes should include:

- source commit SHA;
- CPU and CUDA image digests;
- Python, Torch, CUDA, NumPy, protobuf, protoc, and ParlAI versions;
- CPU verification result;
- GPU model and B2/B3 call identifier;
- checkpoint set used by B1; and
- known limitations.

## Checklist

- [ ] Source tree is clean at the release commit
- [ ] `cpu-build` passes `verify_full_build.sh --accelerator cpu`
- [ ] `cuda-runtime` builds from the same commit
- [ ] CUDA verifier passes with `--require-gpu`
- [ ] B5 returns its adjudication sentinel
- [ ] B1 loads all four checkpoints
- [ ] B2/B3 return the exact PASS result
- [ ] Image tags and digests are recorded
- [ ] Model weights are absent from image layers
- [ ] Release notes link to the evidence

Do not publish a generic `latest` tag until an explicit project policy defines
how it is advanced and rolled back.

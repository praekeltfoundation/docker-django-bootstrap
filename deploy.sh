#!/usr/bin/env bash
set -e

usage() {
  echo "Usage: $0 IMAGE_TAG... [--default DEFAULT_VARIANT] [--dry-run]"
  echo "  IMAGE_TAG : the full image tags for the images to deploy"
  echo "  --default : specify a variant to be tagged as 'latest'"
  echo "  --dry-run : don't run any Docker commands, just print what they would be"
  exit 1
}

DEFAULT_VARIANT=""
DRY_RUN="NO"
IMAGE_TAGS=()
while [[ $# > 0 ]]; do
  key="$1"; shift

  case "$key" in
    --default)
      DEFAULT_VARIANT="$1"; shift
      ;;
    --dry-run)
      DRY_RUN="YES"
      ;;
    *)
      IMAGE_TAGS+=("$key")
      ;;
  esac
done

if [[ ${#IMAGE_TAGS[@]} == 0 ]]; then
  usage >&2; exit 1
fi

docker_cmd() {
  set -- docker "$@"
  if [[ "$DRY_RUN" == "YES" ]]; then
    echo "$@"
    return
  fi

  "$@"
}

for image_tag in "${IMAGE_TAGS[@]}"; do
  docker_cmd push "$image_tag"

  if [[ -n "$DEFAULT_VARIANT" ]]; then
    # Split the image:tag into image and tag
    IFS=':' read IMAGE TAG <<< "$image_tag"

    if [[ "$TAG" == "$DEFAULT_VARIANT"* ]]; then  # if starts with default
      if [[ "$TAG" == "$DEFAULT_VARIANT" ]]; then  # if equals default
        docker_cmd tag "$image_tag" "$IMAGE:latest"
        docker_cmd push "$IMAGE:latest"
      else
        # Strip the default from the tag
        DEFAULT_TAG="${TAG//$DEFAULT_VARIANT-}"  # alpine-onbuild -> onbuild
        docker_cmd tag "$image_tag" "$IMAGE:$DEFAULT_TAG"
        docker_cmd push "$IMAGE:$DEFAULT_TAG"
      fi
    fi
  fi
done

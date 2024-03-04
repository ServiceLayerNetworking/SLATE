#docker build -t ghcr.io/adiprerepa/slate-global-controller:latest .
#docker push ghcr.io/adiprerepa/slate-global-controller:latest

docker build -t ghcr.io/adiprerepa/slate-controller:latest . &&
docker push ghcr.io/adiprerepa/slate-controller:latest &&
kubectl rollout restart deploy slate-controller

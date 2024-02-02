#docker build -t ghcr.io/adiprerepa/slate-global-controller:latest .
#docker push ghcr.io/adiprerepa/slate-global-controller:latest

docker build -t ghcr.io/adiprerepa/slate-controller-py:latest .
docker push ghcr.io/adiprerepa/slate-controller-py:latest
kubectl rollout restart deploy slate-controller

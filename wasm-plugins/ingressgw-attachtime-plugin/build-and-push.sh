set -e

# for cloudlab
#GOARCH=wasm GOOS=js /usr/local/bin/tinygo build -o wasm-out/slate_plugin.wasm -gc=custom -tags="custommalloc nottinygc_envoy" -scheduler=none -target=wasi main.go

# for aditya: tinygo location is different
GOARCH=wasm GOOS=js /usr/local/bin/tinygo build -o wasm-out/slate_plugin.wasm -scheduler=none -target=wasi ./


docker build -t ghcr.io/adiprerepa/slate-igw-timebomb-plugin:latest .
docker push ghcr.io/adiprerepa/slate-igw-timebomb-plugin:latest

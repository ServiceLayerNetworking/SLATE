set -e

# for cloudlab
GOARCH=wasm GOOS=js /usr/local/bin/tinygo build -o wasm-out/slate_plugin.wasm -gc=custom -tags="custommalloc nottinygc_envoy" -scheduler=none -target=wasi http/main.go
GOARCH=wasm GOOS=js /usr/local/bin/tinygo build -o wasm-out/slate_service.wasm -gc=custom -tags="custommalloc nottinygc_envoy" -scheduler=none -target=wasi wasm-service/main.go

# for aditya: tinygo location is different
#  GOARCH=wasm GOOS=js $HOME/go/bin/tinygo build -o wasm-out/slate_plugin.wasm -gc=custom -tags="custommalloc nottinygc_envoy" -scheduler=none -target=wasi main.go


docker build -t ghcr.io/adiprerepa/slate-plugin:latest .
docker push ghcr.io/adiprerepa/slate-plugin:latest

version=$(cat SLATE_WASMSERVICE_VERSION)
git add wasm-out/slate_service.wasm
git commit -m "Update slate_service.wasm custom version $version"
git push origin main
# increment version
echo $((version+1)) > SLATE_WASMSERVICE_VERSION
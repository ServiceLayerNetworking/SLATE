## wasm with nottinygc
GOARCH=wasm GOOS=js $HOME/go/bin/tinygo build -o wasm-out/slate_plugin.wasm -gc=custom -tags="custommalloc nottinygc_envoy" -scheduler=none -target=wasi main.go

## original
# GOARCH=wasm GOOS=js $HOME/go/bin/tinygo  build -o wasm-out/slate_plugin.wasm -scheduler=none -target=wasi main.go

## example
#tinygo build -o main.wasm -gc=custom -tags=custommalloc -target=wasi -scheduler=none main.go

docker build -t ghcr.io/adiprerepa/slate-plugin:latest .
docker push ghcr.io/adiprerepa/slate-plugin:latest

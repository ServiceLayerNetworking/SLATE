GOARCH=wasm GOOS=js $HOME/go/bin/tinygo  build -o wasm-out/slate_plugin.wasm -scheduler=none -target=wasi main.go
docker build -t ghcr.io/adiprerepa/slate-plugin:latest .
docker push ghcr.io/adiprerepa/slate-plugin:latest

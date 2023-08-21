rm -rf lib;
docker compose -f docker-compose.yaml up --remove-orphans wasm_compile_update; 
docker build -t ghcr.io/adiprerepa/slate-plugin-cpp:latest .;
docker push ghcr.io/adiprerepa/slate-plugin-cpp:latest;

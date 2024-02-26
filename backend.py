from whisper_live.server import TranscriptionServer

def start_backend_server():
    server = TranscriptionServer()
    server.run(
        "localhost",
        port=9090, 
        backend="faster_whisper",
    )

start_backend_server()
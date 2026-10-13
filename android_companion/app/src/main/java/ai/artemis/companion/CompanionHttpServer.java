package ai.artemis.companion;

import android.os.Build;
import android.util.Log;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

final class CompanionHttpServer {
    static final int PORT = 8765;
    private static final String TAG = "ArtemisCompanion";
    private static final int MAX_BODY = 1024 * 1024;

    private final ArtemisAccessibilityService service;
    private final String token;
    private final ExecutorService pool = Executors.newCachedThreadPool();
    private volatile ServerSocket serverSocket;
    private volatile boolean running;

    CompanionHttpServer(ArtemisAccessibilityService service, String token) {
        this.service = service;
        this.token = token;
    }

    void start() {
        running = true;
        Thread thread = new Thread(this::acceptLoop, "artemis-companion-http");
        thread.setDaemon(true);
        thread.start();
    }

    void stop() {
        running = false;
        try {
            if (serverSocket != null) serverSocket.close();
        } catch (IOException ignored) {
        }
        pool.shutdownNow();
    }

    private void acceptLoop() {
        try {
            ServerSocket socket = new ServerSocket();
            socket.setReuseAddress(true);
            socket.bind(new InetSocketAddress(InetAddress.getByName("127.0.0.1"), PORT));
            serverSocket = socket;
            while (running) {
                Socket client = socket.accept();
                pool.execute(() -> handle(client));
            }
        } catch (IOException error) {
            if (running) Log.e(TAG, "loopback server failed", error);
        }
    }

    private void handle(Socket socket) {
        try (Socket client = socket) {
            client.setSoTimeout(20_000);
            InputStream input = new BufferedInputStream(client.getInputStream());
            OutputStream output = client.getOutputStream();

            String requestLine = readLine(input);
            if (requestLine == null || requestLine.isEmpty()) return;
            String[] parts = requestLine.split(" ");
            if (parts.length < 2) return;
            String method = parts[0];
            String path = parts[1];
            int query = path.indexOf('?');
            if (query >= 0) path = path.substring(0, query);

            Map<String, String> headers = new HashMap<>();
            String line;
            while ((line = readLine(input)) != null && !line.isEmpty()) {
                int colon = line.indexOf(':');
                if (colon > 0) {
                    headers.put(line.substring(0, colon).trim().toLowerCase(Locale.ROOT), line.substring(colon + 1).trim());
                }
            }

            if ("/health".equals(path)) {
                send(output, 200, new JSONObject().put("ok", true));
                return;
            }
            if (!path.startsWith("/v1/")) {
                send(output, 404, new JSONObject().put("error", "not found"));
                return;
            }
            if (!("Bearer " + token).equals(headers.get("authorization"))) {
                send(output, 401, new JSONObject().put("error", "unauthorized"));
                return;
            }

            byte[] body = readBody(input, headers);
            JSONObject request = body.length == 0 ? new JSONObject() : new JSONObject(new String(body, StandardCharsets.UTF_8));

            if ("GET".equals(method) && "/v1/device".equals(path)) {
                JSONObject device = new JSONObject()
                        .put("serial", "android-local")
                        .put("state", "device")
                        .put("model", Build.MANUFACTURER + " " + Build.MODEL)
                        .put("transport", "companion");
                JSONArray capabilities = new JSONArray()
                        .put("observe_ui").put("gesture").put("text").put("key").put("launch_app").put("open_link");
                send(output, 200, new JSONObject().put("device", device).put("capabilities", capabilities));
                return;
            }

            if ("POST".equals(method) && "/v1/observe".equals(path)) {
                send(output, 200, service.snapshot().json());
                return;
            }

            if ("POST".equals(method) && "/v1/action".equals(path)) {
                ArtemisAccessibilityService.ExecutionResult result = service.execute(request);
                send(output, result.status, result.json());
                return;
            }

            if ("GET".equals(method) && "/v1/logcat".equals(path)) {
                send(output, 200, new JSONObject().put("text", "Artemis Companion service is running"));
                return;
            }

            send(output, 404, new JSONObject().put("error", "not found"));
        } catch (Exception error) {
            Log.w(TAG, "request failed", error);
        }
    }

    private static byte[] readBody(InputStream input, Map<String, String> headers) throws IOException {
        String rawLength = headers.get("content-length");
        if (rawLength == null) return new byte[0];
        int length = Integer.parseInt(rawLength);
        if (length < 0 || length > MAX_BODY) throw new IOException("request body too large");
        byte[] body = new byte[length];
        int offset = 0;
        while (offset < length) {
            int read = input.read(body, offset, length - offset);
            if (read < 0) throw new IOException("unexpected EOF");
            offset += read;
        }
        return body;
    }

    private static String readLine(InputStream input) throws IOException {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        int value;
        while ((value = input.read()) != -1) {
            if (value == '\n') break;
            if (value != '\r') buffer.write(value);
            if (buffer.size() > 16 * 1024) throw new IOException("header line too long");
        }
        if (value == -1 && buffer.size() == 0) return null;
        return buffer.toString(StandardCharsets.UTF_8.name());
    }

    private static void send(OutputStream output, int status, JSONObject payload) throws IOException {
        byte[] body = payload.toString().getBytes(StandardCharsets.UTF_8);
        String headers = "HTTP/1.1 " + status + " " + reason(status) + "\r\n"
                + "Content-Type: application/json; charset=utf-8\r\n"
                + "Content-Length: " + body.length + "\r\n"
                + "Connection: close\r\n\r\n";
        output.write(headers.getBytes(StandardCharsets.US_ASCII));
        output.write(body);
        output.flush();
    }

    private static String reason(int status) {
        switch (status) {
            case 200: return "OK";
            case 401: return "Unauthorized";
            case 404: return "Not Found";
            case 409: return "Conflict";
            case 422: return "Unprocessable Entity";
            case 423: return "Locked";
            default: return "Error";
        }
    }
}

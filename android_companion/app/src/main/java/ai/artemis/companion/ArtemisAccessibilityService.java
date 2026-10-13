package ai.artemis.companion;

import android.accessibilityservice.AccessibilityService;
import android.accessibilityservice.GestureDescription;
import android.content.Intent;
import android.graphics.Path;
import android.graphics.Rect;
import android.net.Uri;
import android.os.Bundle;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.concurrent.atomic.AtomicLong;

public final class ArtemisAccessibilityService extends AccessibilityService {
    private static volatile ArtemisAccessibilityService active;

    private final AtomicLong sequence = new AtomicLong();
    private CompanionHttpServer server;
    private volatile boolean stopped;

    static boolean isRunning() {
        return active != null;
    }

    @Override
    protected void onServiceConnected() {
        super.onServiceConnected();
        active = this;
        stopped = false;
        server = new CompanionHttpServer(this, CompanionSecurity.token(this));
        server.start();
    }

    @Override
    public void onDestroy() {
        if (server != null) server.stop();
        if (active == this) active = null;
        super.onDestroy();
    }

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
        // Artemis re-observes explicitly before and after actions. Event callbacks are
        // intentionally not used as a hidden source of task truth.
    }

    @Override
    public void onInterrupt() {
        stopped = true;
    }

    UiSnapshot snapshot() {
        return UiSnapshot.capture(this, sequence.incrementAndGet());
    }

    ExecutionResult execute(JSONObject envelope) {
        JSONObject action = envelope.optJSONObject("action");
        JSONObject expectedObservation = envelope.optJSONObject("observation");
        if (action == null) return ExecutionResult.error(422, "missing action");
        if (stopped) return ExecutionResult.error(423, "companion is stopped");

        String type = action.optString("type", "");
        boolean write = !("wait".equals(type) || "finish".equals(type));
        UiSnapshot current = snapshot();

        if (write && expectedObservation != null) {
            String expectedDigest = expectedObservation.optString("digest", "");
            if (!expectedDigest.isEmpty() && !expectedDigest.equals(current.digest)) {
                return ExecutionResult.error(409, "stale observation");
            }
        }

        if (write && getPackageName().equals(current.packageName)) {
            return ExecutionResult.error(423, "companion UI is protected from agent actions");
        }

        try {
            switch (type) {
                case "click":
                    return result(click(action, current, false), "tap accepted");
                case "long_press":
                    return result(click(action, current, true), "long press accepted");
                case "input_text":
                    return result(inputText(action.optString("text", "")), "text accepted");
                case "swipe":
                    return result(swipe(action.optString("direction", "up"), action.optInt("duration_ms", 300), current), "swipe accepted");
                case "press_key":
                    return result(pressKey(action.optString("key", "KEYCODE_BACK")), "key accepted");
                case "launch_app":
                    return result(launchApp(action.optString("package", "")), "app launch accepted");
                case "open_link":
                    return result(openLink(action.optString("url", "")), "link accepted");
                case "wait":
                    Thread.sleep(Math.max(0, Math.min(10_000, action.optLong("delay_ms", 750))));
                    return ExecutionResult.ok("wait complete");
                case "finish":
                    return ExecutionResult.ok("finish acknowledged");
                default:
                    return ExecutionResult.error(422, "unsupported action: " + type);
            }
        } catch (Exception error) {
            return ExecutionResult.error(500, error.toString());
        }
    }

    private ExecutionResult result(boolean ok, String message) {
        return ok ? ExecutionResult.ok(message) : ExecutionResult.error(500, message + " but Android rejected it");
    }

    private boolean click(JSONObject action, UiSnapshot current, boolean longPress) {
        AccessibilityNodeInfo root = getRootInActiveWindow();
        if (root == null) return false;

        AccessibilityNodeInfo node = null;
        if (action.has("target_index")) {
            node = findCandidateByIndex(root, action.optInt("target_index", -1), new int[]{0});
        }
        if (node != null && !longPress) {
            AccessibilityNodeInfo clickable = node;
            for (int depth = 0; clickable != null && depth < 6; depth++) {
                if (clickable.isClickable() && clickable.isEnabled()) {
                    return clickable.performAction(AccessibilityNodeInfo.ACTION_CLICK);
                }
                clickable = clickable.getParent();
            }
        }

        int x;
        int y;
        if (node != null) {
            Rect bounds = new Rect();
            node.getBoundsInScreen(bounds);
            x = bounds.centerX();
            y = bounds.centerY();
        } else {
            JSONArray target = action.optJSONArray("target");
            if (target == null || target.length() < 2) return false;
            x = Math.round((float) target.optInt(0) * current.width / 1000f);
            y = Math.round((float) target.optInt(1) * current.height / 1000f);
        }
        return gesture(x, y, x, y, longPress ? Math.max(550, action.optInt("duration_ms", 700)) : 60);
    }

    private boolean inputText(String text) {
        AccessibilityNodeInfo root = getRootInActiveWindow();
        if (root == null) return false;
        AccessibilityNodeInfo target = root.findFocus(AccessibilityNodeInfo.FOCUS_INPUT);
        if (target == null || !target.isEditable()) target = findEditable(root);
        if (target == null) return false;
        Bundle args = new Bundle();
        args.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text);
        return target.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args);
    }

    private boolean swipe(String direction, int durationMs, UiSnapshot current) {
        int w = current.width;
        int h = current.height;
        int x1 = w / 2, y1 = (int) (h * .75), x2 = w / 2, y2 = (int) (h * .25);
        switch (direction.toLowerCase()) {
            case "down": y1 = (int) (h * .25); y2 = (int) (h * .75); break;
            case "left": x1 = (int) (w * .8); y1 = h / 2; x2 = (int) (w * .2); y2 = h / 2; break;
            case "right": x1 = (int) (w * .2); y1 = h / 2; x2 = (int) (w * .8); y2 = h / 2; break;
            case "up": break;
            default: return false;
        }
        return gesture(x1, y1, x2, y2, Math.max(80, durationMs));
    }

    private boolean pressKey(String key) {
        String normalized = key == null ? "" : key.toUpperCase();
        if (normalized.contains("HOME")) return performGlobalAction(GLOBAL_ACTION_HOME);
        if (normalized.contains("RECENT")) return performGlobalAction(GLOBAL_ACTION_RECENTS);
        if (normalized.contains("NOTIFICATION")) return performGlobalAction(GLOBAL_ACTION_NOTIFICATIONS);
        return performGlobalAction(GLOBAL_ACTION_BACK);
    }

    private boolean launchApp(String packageName) {
        if (packageName == null || packageName.isEmpty()) return false;
        Intent intent = getPackageManager().getLaunchIntentForPackage(packageName);
        if (intent == null) return false;
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        startActivity(intent);
        return true;
    }

    private boolean openLink(String url) {
        if (url == null || url.isEmpty()) return false;
        Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        startActivity(intent);
        return true;
    }

    private boolean gesture(int x1, int y1, int x2, int y2, int durationMs) {
        Path path = new Path();
        path.moveTo(x1, y1);
        if (x1 != x2 || y1 != y2) path.lineTo(x2, y2);
        GestureDescription.StrokeDescription stroke = new GestureDescription.StrokeDescription(path, 0, durationMs);
        GestureDescription gesture = new GestureDescription.Builder().addStroke(stroke).build();
        return dispatchGesture(gesture, null, null);
    }

    private AccessibilityNodeInfo findCandidateByIndex(AccessibilityNodeInfo node, int target, int[] candidateIndex) {
        if (isCandidate(node)) {
            int current = candidateIndex[0]++;
            if (current == target) return node;
        }
        for (int i = 0; i < node.getChildCount(); i++) {
            AccessibilityNodeInfo child = node.getChild(i);
            if (child == null) continue;
            AccessibilityNodeInfo hit = findCandidateByIndex(child, target, candidateIndex);
            if (hit != null) return hit;
        }
        return null;
    }

    private boolean isCandidate(AccessibilityNodeInfo node) {
        Rect bounds = new Rect();
        node.getBoundsInScreen(bounds);
        if (bounds.width() <= 0 || bounds.height() <= 0) return false;
        return nonEmpty(node.getText()) || nonEmpty(node.getContentDescription())
                || nonEmpty(node.getViewIdResourceName()) || node.isClickable();
    }

    private boolean nonEmpty(CharSequence value) {
        return value != null && value.length() > 0;
    }

    private AccessibilityNodeInfo findEditable(AccessibilityNodeInfo node) {
        if (node.isEditable() && node.isEnabled()) return node;
        for (int i = 0; i < node.getChildCount(); i++) {
            AccessibilityNodeInfo child = node.getChild(i);
            if (child == null) continue;
            AccessibilityNodeInfo hit = findEditable(child);
            if (hit != null) return hit;
        }
        return null;
    }

    static final class ExecutionResult {
        final int status;
        final boolean ok;
        final String message;

        private ExecutionResult(int status, boolean ok, String message) {
            this.status = status;
            this.ok = ok;
            this.message = message;
        }

        static ExecutionResult ok(String message) {
            return new ExecutionResult(200, true, message);
        }

        static ExecutionResult error(int status, String message) {
            return new ExecutionResult(status, false, message);
        }

        JSONObject json() {
            try {
                return new JSONObject().put("ok", ok).put("message", message).put("stdout", "").put("stderr", ok ? "" : message);
            } catch (Exception impossible) {
                return new JSONObject();
            }
        }
    }
}

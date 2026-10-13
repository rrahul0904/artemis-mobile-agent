package ai.artemis.companion;

import android.graphics.Rect;
import android.util.DisplayMetrics;
import android.view.accessibility.AccessibilityNodeInfo;

import org.json.JSONException;
import org.json.JSONObject;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

final class UiSnapshot {
    final String xml;
    final String packageName;
    final int width;
    final int height;
    final long sequence;
    final String digest;

    private UiSnapshot(String xml, String packageName, int width, int height, long sequence, String digest) {
        this.xml = xml;
        this.packageName = packageName;
        this.width = width;
        this.height = height;
        this.sequence = sequence;
        this.digest = digest;
    }

    static UiSnapshot capture(ArtemisAccessibilityService service, long sequence) {
        AccessibilityNodeInfo root = service.getRootInActiveWindow();
        String pkg = root == null || root.getPackageName() == null ? "" : root.getPackageName().toString();
        StringBuilder xml = new StringBuilder("<hierarchy>");
        if (root != null) {
            appendNode(root, xml, new int[]{0});
        }
        xml.append("</hierarchy>");

        DisplayMetrics metrics = service.getResources().getDisplayMetrics();
        String body = xml.toString();
        return new UiSnapshot(body, pkg, metrics.widthPixels, metrics.heightPixels, sequence, sha256(pkg + "\n" + body));
    }

    JSONObject json() throws JSONException {
        return new JSONObject()
                .put("hierarchy_xml", xml)
                .put("width", width)
                .put("height", height)
                .put("activity", packageName)
                .put("sequence", sequence)
                .put("digest", digest);
    }

    static AccessibilityNodeInfo findNodeByIndex(AccessibilityNodeInfo root, int target) {
        if (root == null || target < 0) return null;
        return findNodeByIndex(root, target, new int[]{0});
    }

    private static AccessibilityNodeInfo findNodeByIndex(AccessibilityNodeInfo node, int target, int[] counter) {
        int current = counter[0]++;
        if (current == target) return node;
        for (int i = 0; i < node.getChildCount(); i++) {
            AccessibilityNodeInfo child = node.getChild(i);
            if (child == null) continue;
            AccessibilityNodeInfo hit = findNodeByIndex(child, target, counter);
            if (hit != null) return hit;
        }
        return null;
    }

    private static void appendNode(AccessibilityNodeInfo node, StringBuilder out, int[] index) {
        Rect bounds = new Rect();
        node.getBoundsInScreen(bounds);
        out.append("<node")
                .append(" index=\"").append(index[0]++).append("\"")
                .append(" text=\"").append(escape(value(node.getText()))).append("\"")
                .append(" resource-id=\"").append(escape(node.getViewIdResourceName())).append("\"")
                .append(" class=\"").append(escape(value(node.getClassName()))).append("\"")
                .append(" content-desc=\"").append(escape(value(node.getContentDescription()))).append("\"")
                .append(" clickable=\"").append(node.isClickable()).append("\"")
                .append(" editable=\"").append(node.isEditable()).append("\"")
                .append(" enabled=\"").append(node.isEnabled()).append("\"")
                .append(" bounds=\"[").append(bounds.left).append(',').append(bounds.top)
                .append("][").append(bounds.right).append(',').append(bounds.bottom).append("]\"")
                .append('>');
        for (int i = 0; i < node.getChildCount(); i++) {
            AccessibilityNodeInfo child = node.getChild(i);
            if (child != null) appendNode(child, out, index);
        }
        out.append("</node>");
    }

    private static String value(CharSequence value) {
        return value == null ? "" : value.toString();
    }

    private static String escape(String value) {
        if (value == null) return "";
        return value.replace("&", "&amp;")
                .replace("\"", "&quot;")
                .replace("<", "&lt;")
                .replace(">", "&gt;");
    }

    private static String sha256(String text) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] raw = digest.digest(text.getBytes(StandardCharsets.UTF_8));
            StringBuilder out = new StringBuilder("sha256:");
            for (byte value : raw) out.append(String.format("%02x", value & 0xff));
            return out.toString();
        } catch (Exception impossible) {
            throw new IllegalStateException(impossible);
        }
    }
}

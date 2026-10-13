package ai.artemis.companion;

import android.app.Activity;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.graphics.Typeface;
import android.os.Bundle;
import android.provider.Settings;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

public final class MainActivity extends Activity {
    private TextView status;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        int pad = Math.round(24 * getResources().getDisplayMetrics().density);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(pad, pad, pad, pad);
        root.setLayoutParams(new ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

        TextView title = new TextView(this);
        title.setText("Artemis Companion");
        title.setTextSize(28);
        title.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        root.addView(title);

        TextView description = new TextView(this);
        description.setText("Device-native execution transport for Artemis. The service is loopback-only and starts only after you enable Accessibility.");
        description.setTextSize(16);
        description.setPadding(0, pad / 2, 0, pad / 2);
        root.addView(description);

        status = new TextView(this);
        status.setTextSize(18);
        root.addView(status);

        Button accessibility = new Button(this);
        accessibility.setText("Open Accessibility settings");
        accessibility.setOnClickListener(v -> startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)));
        root.addView(accessibility);

        TextView endpoint = new TextView(this);
        endpoint.setText("Endpoint: http://127.0.0.1:8765");
        endpoint.setTextSize(16);
        endpoint.setPadding(0, pad, 0, pad / 3);
        root.addView(endpoint);

        String token = CompanionSecurity.token(this);
        TextView tokenLabel = new TextView(this);
        tokenLabel.setText("Per-install bearer token:");
        tokenLabel.setTextSize(16);
        root.addView(tokenLabel);

        TextView tokenView = new TextView(this);
        tokenView.setText(token);
        tokenView.setTypeface(Typeface.MONOSPACE);
        tokenView.setTextIsSelectable(true);
        tokenView.setPadding(0, pad / 3, 0, pad / 3);
        root.addView(tokenView);

        Button copy = new Button(this);
        copy.setText("Copy token");
        copy.setOnClickListener(v -> {
            ClipboardManager clipboard = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
            clipboard.setPrimaryClip(ClipData.newPlainText("Artemis Companion token", token));
            Toast.makeText(this, "Token copied", Toast.LENGTH_SHORT).show();
        });
        root.addView(copy);

        TextView warning = new TextView(this);
        warning.setText("Keep this token private. Artemis still verifies postconditions after the companion accepts an action; transport acceptance is not task success.");
        warning.setPadding(0, pad, 0, 0);
        root.addView(warning);

        setContentView(root);
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (status != null) {
            status.setText(ArtemisAccessibilityService.isRunning()
                    ? "Status: Accessibility service running"
                    : "Status: Accessibility service not running");
        }
    }
}

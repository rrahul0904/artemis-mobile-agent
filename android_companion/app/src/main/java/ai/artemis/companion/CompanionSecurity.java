package ai.artemis.companion;

import android.content.Context;
import android.content.SharedPreferences;

import java.security.SecureRandom;

final class CompanionSecurity {
    private static final String PREFS = "artemis_companion";
    private static final String TOKEN = "bearer_token";

    private CompanionSecurity() {}

    static synchronized String token(Context context) {
        SharedPreferences prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        String existing = prefs.getString(TOKEN, null);
        if (existing != null && existing.length() >= 32) {
            return existing;
        }
        byte[] random = new byte[32];
        new SecureRandom().nextBytes(random);
        StringBuilder out = new StringBuilder(random.length * 2);
        for (byte value : random) {
            out.append(String.format("%02x", value & 0xff));
        }
        String generated = out.toString();
        prefs.edit().putString(TOKEN, generated).apply();
        return generated;
    }
}

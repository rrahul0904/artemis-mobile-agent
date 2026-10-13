plugins {
    id("com.android.application")
}

android {
    namespace = "ai.artemis.companion"
    compileSdk = 35

    defaultConfig {
        applicationId = "ai.artemis.companion"
        minSdk = 30
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }
}

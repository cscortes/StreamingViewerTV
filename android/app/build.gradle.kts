plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

android {
    namespace = "com.streamingviewertv.app"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.streamingviewertv.app"
        minSdk = 24
        targetSdk = 35
        versionCode = 1
        versionName = "0.3.6"

        ndk {
            // Real devices + current emulators. Drop x86_64 later to shrink APK if needed.
            abiFilters += listOf("arm64-v8a", "x86_64")
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        viewBinding = true
    }

    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }
}

chaquopy {
    defaultConfig {
        version = "3.10"
        // Prefer CHAQUOPY_PYTHON (CI/local override). Otherwise Chaquopy finds
        // python3.10 on PATH — do not hardcode a machine-specific path.
        val chaquopyPython = System.getenv("CHAQUOPY_PYTHON")
        if (!chaquopyPython.isNullOrBlank()) {
            buildPython(chaquopyPython)
        }
        // Ensure static/ + templates/ exist as real files for StaticFiles/Jinja2.
        extractPackages("stream_viewer")
        pip {
            // Plain uvicorn (no [standard]) avoids uvloop on Android.
            // Pydantic v1 avoids pydantic-core (Rust) wheels that Chaquopy may lack.
            // httpx instead of httpx2: httpx2>=2.5 needs idna>=3.18, not on Chaquopy's index.
            // stream_viewer.app falls back to `import httpx as httpx2`.
            install("fastapi==0.110.3")
            install("uvicorn==0.29.0")
            install("jinja2==3.1.6")
            install("httpx==0.27.2")
            install("pydantic==1.10.21")
            install("starlette==0.37.2")
            install("anyio==4.7.0")
            install("sniffio==1.3.1")
            install("click==8.1.8")
            install("h11==0.14.0")
            install("typing-extensions==4.12.2")
            install("markupsafe==3.0.3")
            install("httpcore==1.0.7")
            install("certifi")
            install("idna")
        }
    }
    sourceSets {
        getByName("main") {
            // Populated by syncPythonSources from the repo's stream_viewer package.
            setSrcDirs(listOf("src/main/python"))
        }
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
    implementation("androidx.constraintlayout:constraintlayout:2.2.0")
    implementation("androidx.webkit:webkit:1.12.1")
}

val syncPythonSources by tasks.registering(Copy::class) {
    description = "Copy stream_viewer into Chaquopy python sources (excludes builder)."
    from(rootProject.file("../stream_viewer")) {
        exclude("**/__pycache__/**")
        exclude("**/*.pyc")
    }
    into(layout.projectDirectory.dir("src/main/python/stream_viewer"))
}

tasks.named("preBuild") {
    dependsOn(syncPythonSources)
}

// Chaquopy merges python sources after our copy; declare the dependency explicitly.
afterEvaluate {
    tasks.matching { it.name.startsWith("merge") && it.name.endsWith("PythonSources") }.configureEach {
        dependsOn(syncPythonSources)
    }
}

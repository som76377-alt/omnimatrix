import java.util.Base64

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

val updateKeystoreEncoded = System.getenv("ANDROID_KEYSTORE_BASE64").orEmpty().trim()
val updateStorePassword = System.getenv("ANDROID_KEYSTORE_PASSWORD").orEmpty()
val updateKeyAlias = System.getenv("ANDROID_KEY_ALIAS").orEmpty()
val updateKeyPassword = System.getenv("ANDROID_KEY_PASSWORD").orEmpty()
val hasPersistentUpdateSigner = updateKeystoreEncoded.isNotBlank()
val stableKeystoreFile = layout.buildDirectory.file("signing/omnitrix-updates.p12").get().asFile
if (hasPersistentUpdateSigner) {
    if (updateStorePassword.isBlank() || updateKeyAlias.isBlank() || updateKeyPassword.isBlank()) {
        throw GradleException("Persistent Android signing is only partially configured. Set all four ANDROID_* signing secrets.")
    }
    try {
        stableKeystoreFile.parentFile.mkdirs()
        stableKeystoreFile.writeBytes(Base64.getMimeDecoder().decode(updateKeystoreEncoded))
    } catch (error: Exception) {
        throw GradleException("Could not decode the persistent Android signing keystore.", error)
    }
}
val requestedVersionCode = providers.gradleProperty("omnitrixVersionCode").orNull
    ?.toIntOrNull()?.coerceAtLeast(2) ?: 2

android {
    namespace = "com.omnitrix.mobile"
    compileSdk = 36
    defaultConfig {
        applicationId = "com.omnitrix.mobile"
        minSdk = 26
        targetSdk = 35
        versionCode = requestedVersionCode
        versionName = if (requestedVersionCode > 2) "0.3." + requestedVersionCode else "0.2.0"
        buildConfigField("boolean", "AUTO_UPDATES_ENABLED", hasPersistentUpdateSigner.toString())
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }
    signingConfigs {
        if (hasPersistentUpdateSigner) {
            create("persistentUpdate") {
                storeFile = stableKeystoreFile
                storePassword = updateStorePassword
                keyAlias = updateKeyAlias
                keyPassword = updateKeyPassword
            }
        }
    }
    buildTypes {
        debug {
            applicationIdSuffix = ".debug"
            versionNameSuffix = "-debug"
            if (hasPersistentUpdateSigner) signingConfig = signingConfigs.getByName("persistentUpdate")
        }
        release {
            isMinifyEnabled = false
            if (hasPersistentUpdateSigner) signingConfig = signingConfigs.getByName("persistentUpdate")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures {
        compose = true
        buildConfig = true
    }
    packaging { resources { excludes += "/META-INF/{AL2.0,LGPL2.1}" } }
}

dependencies {
    implementation(platform("androidx.compose:compose-bom:2025.12.00"))
    implementation("androidx.activity:activity-compose:1.11.0")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.10.2")
    implementation("androidx.security:security-crypto:1.1.0")
    debugImplementation("androidx.compose.ui:ui-tooling")
    testImplementation("junit:junit:4.13.2")
}


val pixelFontBase64 = layout.projectDirectory.file("../fonts/PixelifySans.ttf.b64")
val pixelFontOutput = layout.buildDirectory.file("generated/res/pixelFont/font/pixelify_sans.ttf")

val decodePixelFont by tasks.registering {
    inputs.file(pixelFontBase64)
    outputs.file(pixelFontOutput)
    doLast {
        val inputFile = pixelFontBase64.asFile
        if (!inputFile.isFile) {
            throw GradleException("Pixelify Sans source file is missing: " + inputFile.path)
        }
        val outputFile = pixelFontOutput.get().asFile
        outputFile.parentFile.mkdirs()
        outputFile.writeBytes(Base64.getMimeDecoder().decode(inputFile.readText(Charsets.UTF_8)))
    }
}

android.sourceSets.getByName("main").res.srcDir(layout.buildDirectory.dir("generated/res/pixelFont"))
tasks.named("preBuild").configure { dependsOn(decodePixelFont) }

plugins {
 id("com.android.application")
 id("org.jetbrains.kotlin.android")
 id("org.jetbrains.kotlin.plugin.compose")
 id("com.google.devtools.ksp")
}
android {
 namespace = "ru.replika"
 compileSdk = 35
 ndkVersion = "27.2.12479018"
 if (!providers.gradleProperty("skipWhisperBuild").isPresent) { externalNativeBuild { cmake { path = file("src/main/cpp/CMakeLists.txt"); version = "3.22.1" } } }
 defaultConfig {
  applicationId = "ru.replika.offline"; minSdk = 26; targetSdk = 35
  versionCode = 3; versionName = "1.2.0"
  ndk { abiFilters += listOf("arm64-v8a", "x86_64") }
  testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
 }
 buildFeatures { compose = true; buildConfig = true }
 compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
 kotlinOptions { jvmTarget = "17" }
 // Avoid inflating the large debug DEX on the startup thread (observed ART startup ANR).
 packaging { jniLibs.useLegacyPackaging = false; dex.useLegacyPackaging = false }
 testOptions { unitTests.isReturnDefaultValues = true }
}
dependencies {
 implementation(platform("androidx.compose:compose-bom:2025.04.01"))
 implementation("androidx.activity:activity-compose:1.10.1")
 implementation("androidx.compose.material3:material3")
 implementation("androidx.compose.material:material-icons-extended")
 implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.7")
 implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.7")
 implementation("androidx.room:room-runtime:2.7.1")
 implementation("androidx.room:room-ktx:2.7.1")
 ksp("androidx.room:room-compiler:2.7.1")
 implementation("androidx.media3:media3-exoplayer:1.6.1")
 implementation("androidx.work:work-runtime-ktx:2.10.1")
 implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.10.2")
 implementation("androidx.core:core-ktx:1.16.0")
 implementation("org.apache.commons:commons-compress:1.27.1")
 testImplementation("junit:junit:4.13.2")
 testImplementation("org.json:json:20250107")
 androidTestImplementation("androidx.test.ext:junit:1.2.1")
 androidTestImplementation("androidx.test:runner:1.6.2")
 androidTestImplementation("androidx.test.espresso:espresso-core:3.6.1")
 androidTestImplementation(platform("androidx.compose:compose-bom:2025.04.01"))
 androidTestImplementation("androidx.compose.ui:ui-test-junit4")
 debugImplementation("androidx.compose.ui:ui-test-manifest")
}

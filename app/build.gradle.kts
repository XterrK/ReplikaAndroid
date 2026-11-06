plugins {
 id("com.android.application")
 id("org.jetbrains.kotlin.android")
 id("org.jetbrains.kotlin.plugin.compose")
 id("com.google.devtools.ksp")
}

// Models remain local build inputs. Only the All-in-One variants package this generated asset.
val embeddedAssets = layout.buildDirectory.dir("generated/embedded-models/assets")
// Explicit opt-in candidate builds retain the V1.6 default for ordinary builds.
val defaultAsrPlan = providers.gradleProperty("replikaAsrPlan").orElse("v16").get()
require(defaultAsrPlan in setOf("v16", "vad_words_none", "vad_words_seam", "vad_words_short15",
 "vad_words_short10", "vad_words_sensitive", "vad_words_short10_seam", "vad_words_sensitive_short10",
 "vad_words_context300", "vad_words_context600")) { "Unsupported replikaAsrPlan" }
val prepareEmbeddedModelPack by tasks.registering(Exec::class) {
 group = "replika"
 description = "Verify and package the existing local offline models without downloading weights"
 val sourcePack = rootProject.file("model-pack/replika-offline-pack-v1.5.zip")
 val modelManifest = file("src/main/assets/models-lock.json")
 val generator = rootProject.file("tools/prepare_embedded_pack.py")
 val outputPack = embeddedAssets.map { it.file("offline/replika-models.zip") }
 val metadata = layout.buildDirectory.file("generated/embedded-models/pack-verification.json")
 inputs.files(sourcePack, modelManifest, generator)
 outputs.files(outputPack, metadata)
 workingDir(rootProject.projectDir)
 commandLine(
  providers.gradleProperty("replikaPython").orElse("python3").get(), generator.absolutePath,
  "--source", sourcePack.absolutePath, "--manifest", modelManifest.absolutePath,
  "--output", outputPack.get().asFile.absolutePath,
  "--metadata", metadata.get().asFile.absolutePath,
 )
}

android {
 namespace = "ru.replika"
 compileSdk = 35
 ndkVersion = "27.2.12479018"
 defaultConfig {
  applicationId = "ru.replika.offline"; minSdk = 26; targetSdk = 35
  versionCode = 8; versionName = "1.6"
  buildConfigField("boolean", "BUNDLED_MODELS", "false")
  buildConfigField("String", "DEFAULT_ASR_PLAN", "\"$defaultAsrPlan\"")
  buildConfigField("String", "EMBEDDED_MODEL_ASSET", "\"offline/replika-models.zip\"")
  // Model SHA-256 values come from models-lock.json; the generated ZIP fingerprint is build evidence.
  buildConfigField("String", "EMBEDDED_MODEL_PACK_SHA256", "\"\"")
  testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
 }
 // Retain update compatibility after moving the workspace to another computer.
 // Local development key is intentionally excluded from Git.
 val portableDebugKey = rootProject.file("local-dev/debug.keystore")
 if (portableDebugKey.isFile) signingConfigs.getByName("debug") {
  storeFile = portableDebugKey
  storePassword = "android"; keyAlias = "androiddebugkey"; keyPassword = "android"
 }
 buildTypes {
  getByName("debug") { ndk { abiFilters += listOf("arm64-v8a", "x86_64") } }
  getByName("release") { ndk { abiFilters += listOf("arm64-v8a", "x86_64") } }
  create("allInOne") {
   initWith(getByName("debug"))
   signingConfig = signingConfigs.getByName("debug")
   matchingFallbacks += "debug"
   ndk { abiFilters.clear(); abiFilters += "arm64-v8a" }
   buildConfigField("boolean", "BUNDLED_MODELS", "true")
  }
  create("allInOneQa") {
   initWith(getByName("debug"))
   signingConfig = signingConfigs.getByName("debug")
   matchingFallbacks += "debug"
   // QA normally has isolated data. Explicit same-ID mode permits a controlled emulator upgrade test.
   if (!providers.gradleProperty("replikaAioQaSameId").map { it.toBoolean() }.getOrElse(false)) {
    applicationIdSuffix = ".aioqa"
   }
   ndk { abiFilters.clear(); abiFilters += "x86_64" }
   buildConfigField("boolean", "BUNDLED_MODELS", "true")
  }
 }
 sourceSets {
  getByName("allInOne").assets.srcDir(embeddedAssets)
  getByName("allInOneQa").assets.srcDir(embeddedAssets)
 }
 testBuildType = providers.gradleProperty("replikaTestBuildType").getOrElse("debug")
 // The inner ZIP is already compressed; avoid a second decompression layer during first launch.
 androidResources { noCompress += "zip" }
 buildFeatures { compose = true; buildConfig = true }
 compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
 kotlinOptions { jvmTarget = "17" }
 // Avoid inflating the large debug DEX on the startup thread (observed ART startup ANR).
 packaging { jniLibs.useLegacyPackaging = false; dex.useLegacyPackaging = false }
 testOptions { unitTests.isReturnDefaultValues = true }
}
// AGP shares identical native Debug configurations across build types. Their preBuild tasks can
// therefore run during a standard build; only AIO asset merging may depend on the local model pack.
tasks.matching { it.name == "mergeAllInOneAssets" || it.name == "mergeAllInOneQaAssets" }.configureEach {
 dependsOn(prepareEmbeddedModelPack)
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
 implementation("androidx.datastore:datastore-preferences:1.1.4")
 implementation("org.apache.commons:commons-compress:1.27.1")
 testImplementation("junit:junit:4.13.2")
 testImplementation("org.json:json:20250107")
 androidTestImplementation("androidx.test.ext:junit:1.2.1")
 androidTestImplementation("androidx.test:runner:1.6.2")
 androidTestImplementation("androidx.test.espresso:espresso-core:3.6.1")
 androidTestImplementation(platform("androidx.compose:compose-bom:2025.04.01"))
 androidTestImplementation("androidx.compose.ui:ui-test-junit4")
 debugImplementation("androidx.compose.ui:ui-test-manifest")
 add("allInOneQaImplementation", "androidx.compose.ui:ui-test-manifest")
}

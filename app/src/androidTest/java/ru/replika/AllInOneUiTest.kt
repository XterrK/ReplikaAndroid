package ru.replika

import android.graphics.Bitmap
import androidx.activity.compose.setContent
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.unit.Density
import androidx.lifecycle.ViewModelProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assume
import org.junit.Rule
import org.junit.Test
import org.junit.rules.ExternalResource
import org.junit.rules.RuleChain
import org.junit.rules.TestRule
import org.junit.runner.RunWith
import ru.replika.ml.BundledModelCoordinator
import ru.replika.ui.AppViewModel
import ru.replika.ui.ModelPreparationScreen
import ru.replika.ui.ReplikaTheme
import java.io.File
import java.util.concurrent.atomic.AtomicInteger

/** Real Models integration plus an explicitly isolated rendering fixture for the recovery screen. */
@RunWith(AndroidJUnit4::class)
class AllInOneUiTest {
    private val compose = createAndroidComposeRule<MainActivity>()
    private val app: ReplikaApp
        get() = InstrumentationRegistry.getInstrumentation().targetContext.applicationContext as ReplikaApp

    // Outer rule finishes real provisioning before the Compose rule launches the Activity.
    @get:Rule
    val rules: TestRule = RuleChain.outerRule(object : ExternalResource() {
        override fun before() {
            Assume.assumeTrue("Requires an All-in-One variant", BuildConfig.BUNDLED_MODELS)
            runBlocking { withTimeout(10 * 60 * 1000L) { app.bundledModels.awaitReady() } }
        }
    }).around(compose)

    @Test
    fun installedBundleHasSingleGigaBackendAndOptionalAdvancedImport() {
        compose.onNodeWithTag("tab-library").performClick()
        compose.onNodeWithTag("library-search").assertIsDisplayed()
        compose.onNodeWithTag("tab-models").performClick()
        compose.waitUntil(120_000) {
            compose.onAllNodesWithText("Модели проверены.", substring = true)
                .fetchSemanticsNodes().isNotEmpty()
        }
        compose.onNodeWithTag("models-bundled-status").assertIsDisplayed()
        compose.onNodeWithText("Импорт offline pack").assertDoesNotExist()
        compose.onNodeWithTag("models-restore-bundled").assertDoesNotExist()
        capture("06-models-bundled-ready.png")

        compose.onNodeWithText("Whisper tiny").assertDoesNotExist()
        compose.onNodeWithTag("asr-current").assertExists()
        var actualBackend=""
        compose.activityRule.scenario.onActivity { activity ->
            actualBackend=ViewModelProvider(activity)[AppViewModel::class.java].backend.value
        }
        assertEquals(app.models.asrId,actualBackend)
            compose.onNodeWithTag("models-list").performScrollToNode(hasTestTag("models-advanced-toggle"))
            compose.onNodeWithTag("models-advanced-toggle").assertHasClickAction().performClick()
            compose.onNodeWithTag("models-list").performScrollToNode(hasText("Импорт offline pack"))
            compose.onNodeWithText("Импорт offline pack").assertIsDisplayed().assertIsEnabled().assertHasClickAction()
            compose.onNodeWithTag("models-restore-bundled").assertExists().assertIsEnabled().assertHasClickAction()
            capture("07-models-advanced-optional.png")

            compose.onNodeWithTag("models-list").performScrollToNode(hasTestTag("models-advanced-toggle"))
            compose.onNodeWithTag("models-advanced-toggle").performClick()
            compose.onNodeWithText("Импорт offline pack").assertDoesNotExist()
            compose.onNodeWithTag("models-restore-bundled").assertDoesNotExist()
            File(app.filesDir, "all-in-one-models-ui.json").writeText(JSONObject()
                .put("package", app.packageName).put("realInstalledModels", true)
                .put("advancedInitiallyCollapsed", true).put("singleGigaBackend", actualBackend)
                .put("optionalImportAndRestoreAccessible", true).put("importOrRestoreInvoked", false)
                .put("newInferencePerformed", false).toString(2))
        compose.onNodeWithTag("tab-library").performClick()
        compose.onNodeWithTag("library-search").assertIsDisplayed()
    }

    @Test
    fun preparationErrorRetryRemainsAccessibleWithLongTextAtFontScale130() {
        val retried = AtomicInteger()
        val message = "UI-тест состояния ошибки. Не удалось подготовить встроенные модели. " +
            "Освободите место во внутреннем хранилище и повторите подготовку. " +
            "Уже проверенные файлы и ваши записи сохранены. " +
            "Это длинное объяснение проверяет доступность действия на небольшом экране " +
            "при увеличенном размере текста и не является результатом реального сбоя ML."
        compose.activityRule.scenario.onActivity { activity ->
            activity.setContent {
                val originalDensity = LocalDensity.current
                CompositionLocalProvider(LocalDensity provides Density(originalDensity.density, fontScale = 1.3f)) {
                    ReplikaTheme {
                        ModelPreparationScreen(
                            state = BundledModelCoordinator.State(BundledModelCoordinator.Phase.ERROR, message = message),
                            onRetry = { retried.incrementAndGet() },
                        )
                    }
                }
            }
        }
        compose.onNodeWithTag("model-preparation").assertExists()
        compose.onNodeWithText("Подготовка не завершена").assertExists()
        compose.onNodeWithText(message).assertExists()
        compose.onNodeWithTag("retry-preparation").performScrollTo()
            .assertIsDisplayed().assertIsEnabled().assertHasClickAction().performClick()
        compose.runOnIdle { assertEquals(1, retried.get()) }
        capture("08-ui-fixture-error-font130.png")
        File(app.filesDir, "all-in-one-preparation-error-ui-fixture.json").writeText(JSONObject()
            .put("explicitUiRenderingFixture", true).put("actualInstallerFailureInjected", false)
            .put("newInferencePerformed", false).put("localComposeFontScale", 1.3)
            .put("longExplanationReadableByScrolling", true).put("retryCallbackCount", retried.get())
            .put("scope", "Recovery-screen rendering and accessible retry callback only; no model preparation claim").toString(2))
    }

    private fun capture(name: String) {
        compose.waitForIdle()
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        instrumentation.waitForIdleSync()
        val folder = File(app.filesDir, "human-review-v1.2.1").apply { mkdirs() }
        val target = File(folder, name)
        if (target.exists()) check(target.renameTo(File(folder, name.removeSuffix(".png") + "-${System.nanoTime()}.png")))
        val image = instrumentation.uiAutomation.takeScreenshot() ?: error("Android returned no screenshot")
        try {
            target.outputStream().use { image.compress(Bitmap.CompressFormat.PNG, 100, it) }
        } finally {
            image.recycle()
        }
    }
}

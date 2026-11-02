package ru.replika
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.*
import org.junit.runner.RunWith
@RunWith(AndroidJUnit4::class)
class NavigationTest {
 @get:Rule val compose=createAndroidComposeRule<MainActivity>()
 @Test fun libraryModelsNavigation() {
  compose.onNodeWithText("Библиотека").assertIsDisplayed()
  compose.onNodeWithTag("library-search").assertIsDisplayed()
  compose.onNodeWithText("Модели").performClick()
  compose.onNodeWithText("Распознавание на устройстве").assertIsDisplayed()
  if(BuildConfig.BUNDLED_MODELS) {
   compose.onNodeWithTag("models-list").performScrollToNode(hasTestTag("models-advanced-toggle"))
   compose.onNodeWithTag("models-advanced-toggle").performClick()
   compose.onNodeWithTag("models-list").performScrollToNode(hasText("Импорт offline pack"))
  }
  compose.onNodeWithText("Импорт offline pack").assertIsDisplayed()
  compose.onNodeWithText("Записи").performClick()
  compose.onNodeWithText("Библиотека").assertIsDisplayed()
  compose.onNodeWithTag("library-search").assertIsDisplayed()
 }
}

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
  compose.onNodeWithText("Каждое слово\nможно проверить.").assertIsDisplayed()
  compose.onNodeWithText("Модели").performClick()
  compose.onNodeWithText("ЛОКАЛЬНЫЙ ИНТЕЛЛЕКТ").assertIsDisplayed()
  compose.onNodeWithText("Записи").performClick()
  compose.onNodeWithText("Начните с голоса").assertIsDisplayed()
 }
}

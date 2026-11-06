package ru.replika.data

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.map

enum class ThemeMode(val label: String) { SYSTEM("Как в системе"), LIGHT("Светлая"), DARK("Тёмная") }
private val Context.appearanceStore by preferencesDataStore(name="appearance")
class AppearancePreferences(private val context: Context) {
 private val key=stringPreferencesKey("theme")
 val mode=context.appearanceStore.data.map { prefs -> ThemeMode.entries.firstOrNull { it.name==prefs[key] }?:ThemeMode.SYSTEM }
 suspend fun select(mode: ThemeMode) { context.appearanceStore.edit { it[key]=mode.name } }
}

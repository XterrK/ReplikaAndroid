package ru.replika.ml

import android.content.Context
import android.content.Intent
import android.net.Uri

/**
 * Durable read access to a user-picked document (ACTION_OPEN_DOCUMENT grants are persistable).
 * Used when a large original is processed in place instead of being copied into app storage.
 */
open class SourceGrants(private val context: Context) {
 /** Whether REPLIKA already holds a durable read grant for [uri]. */
 open fun held(uri: Uri): Boolean = runCatching {
  context.contentResolver.persistedUriPermissions.any { it.uri==uri && it.isReadPermission }
 }.getOrDefault(false)
 /** Takes a durable read grant; false when the provider or picker did not offer one. */
 open fun hold(uri: Uri): Boolean = try {
  context.contentResolver.takePersistableUriPermission(uri,Intent.FLAG_GRANT_READ_URI_PERMISSION);true
 } catch(_: SecurityException) { false }
 open fun release(uri: Uri) {
  runCatching { context.contentResolver.releasePersistableUriPermission(uri,Intent.FLAG_GRANT_READ_URI_PERMISSION) }
 }
}

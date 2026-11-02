package ru.replika
import android.app.Application
import androidx.room.Room
import ru.replika.data.ReplikaDatabase
import ru.replika.ml.ModelManager
import ru.replika.ml.BundledModelCoordinator
class ReplikaApp: Application() {
 val db by lazy { Room.databaseBuilder(this,ReplikaDatabase::class.java,"replika.db").build() }
 val models by lazy { ModelManager(this) }
 val bundledModels by lazy { BundledModelCoordinator(this) }
 override fun onCreate() { super.onCreate();bundledModels.start() }
}

package ru.replika.data

import androidx.room.*
import kotlinx.coroutines.flow.Flow
import org.json.JSONArray
import ru.replika.domain.Segment

@Entity(tableName="recordings")
data class Recording(
 @PrimaryKey val id: String, val title: String, val audioPath: String,
 val createdAt: Long = System.currentTimeMillis(), val durationMs: Long = 0,
 val status: String = "IMPORTED", val phase: String = "Готово к обработке", val error: String? = null,
 val peaks: String = "", val diagnostics: String = "", val backend: String = "giga-v2", val expectedSpeakers: Int = -1
)
@Entity(tableName="segments", foreignKeys=[ForeignKey(entity=Recording::class,parentColumns=["id"],childColumns=["recordingId"],onDelete=ForeignKey.CASCADE)], indices=[Index("recordingId")])
data class SegmentRow(
 @PrimaryKey val id: String, val recordingId: String, val startMs: Long, val endMs: Long,
 val speakerId: Int, val text: String, val source: String, val edited: Boolean = false,
 val reasons: String = "[]", val reviewed: Boolean = false
) {
 fun domain() = Segment(id,startMs,endMs,speakerId,text,source,edited, List(JSONArray(reasons).length()) { JSONArray(reasons).getString(it) },reviewed)
 companion object { fun from(r: String,s: Segment) = SegmentRow(s.id,r,s.startMs,s.endMs,s.speakerId,s.text,s.source,s.edited,JSONArray(s.reasons).toString(),s.reviewed) }
}
@Entity(tableName="speakers",primaryKeys=["recordingId","speakerId"])
data class SpeakerRow(val recordingId: String,val speakerId: Int,val name: String)
@Dao
abstract class ReplikaDao {
 @Query("SELECT * FROM recordings ORDER BY createdAt DESC") abstract fun recordings(): Flow<List<Recording>>
 @Query("SELECT * FROM recordings WHERE id=:id") abstract suspend fun recording(id: String): Recording?
 @Query("SELECT * FROM segments WHERE recordingId=:id ORDER BY startMs,endMs") abstract fun segments(id: String): Flow<List<SegmentRow>>
 @Query("SELECT * FROM segments WHERE recordingId=:id ORDER BY startMs,endMs") abstract suspend fun segmentList(id: String): List<SegmentRow>
 @Query("SELECT * FROM speakers WHERE recordingId=:id") abstract fun speakers(id: String): Flow<List<SpeakerRow>>
 @Upsert abstract suspend fun insert(recording: Recording)
 @Insert(onConflict=OnConflictStrategy.REPLACE) abstract suspend fun insertSegments(rows: List<SegmentRow>)
 @Update abstract suspend fun updateSegment(row: SegmentRow)
 @Insert(onConflict=OnConflictStrategy.REPLACE) abstract suspend fun speaker(speaker: SpeakerRow)
 @Query("DELETE FROM segments WHERE recordingId=:id") abstract suspend fun clearSegments(id: String)
 @Query("UPDATE recordings SET status=:status,phase=:phase,error=:error WHERE id=:id") abstract suspend fun status(id: String,status: String,phase: String,error: String?=null)
 @Query("SELECT DISTINCT recordingId FROM segments WHERE text LIKE '%' || :query || '%'") abstract suspend fun search(query: String): List<String>
 @Transaction open suspend fun complete(recording: Recording, rows: List<SegmentRow>) {
  clearSegments(recording.id); insertSegments(rows); insert(recording)
 }
}
@Database(entities=[Recording::class,SegmentRow::class,SpeakerRow::class],version=1,exportSchema=false)
abstract class ReplikaDatabase: RoomDatabase() { abstract fun dao(): ReplikaDao }

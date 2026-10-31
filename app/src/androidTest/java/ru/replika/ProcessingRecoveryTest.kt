package ru.replika

import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.ViewModelStore
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import ru.replika.data.Recording
import ru.replika.data.SegmentRow
import ru.replika.domain.Segment
import ru.replika.ui.AppViewModel

@RunWith(AndroidJUnit4::class)
class ProcessingRecoveryTest {
 @Test fun orphanedProgressRecoversWithoutDeletingSavedEdits()=runBlocking {
  val instrumentation=InstrumentationRegistry.getInstrumentation()
  val app=instrumentation.targetContext.applicationContext as ReplikaApp
  val dao=app.db.dao();val prefix="recovery-${System.nanoTime()}"
  val failed="$prefix-failed";val cancelled="$prefix-cancelled"
  dao.insert(Recording(failed,"orphan processing","absent.wav",status="PROCESSING"))
  val saved=SegmentRow.from(failed,Segment(id="$prefix-segment",startMs=0,endMs=1000,speakerId=1,text="Сохранённая правка",source="explicit persistence fixture",edited=true))
  dao.insertSegments(listOf(saved))
  dao.insert(Recording(cancelled,"orphan cancellation","absent.wav",status="CANCELLING"))
  val store=ViewModelStore();lateinit var vm: AppViewModel
  app.models.gate.lock();var ownGate=true
  try {
   instrumentation.runOnMainSync { vm=ViewModelProvider(store,ViewModelProvider.AndroidViewModelFactory.getInstance(app))[AppViewModel::class.java] }
   val recovering=async(Dispatchers.Main) { vm.reconcileProcessing() }
   delay(300)
   assertFalse("Recovery must wait for native gate",recovering.isCompleted)
   assertEquals("CANCELLING",dao.recording(cancelled)!!.status)
   app.models.gate.unlock();ownGate=false
   withTimeout(10000) { recovering.await() }
   assertEquals("ERROR",dao.recording(failed)!!.status)
   assertEquals("CANCELLED",dao.recording(cancelled)!!.status)
   assertEquals(saved,dao.segmentList(failed).single())
  } finally {
   if(ownGate) app.models.gate.unlock()
   instrumentation.runOnMainSync { store.clear() }
   app.db.openHelper.writableDatabase.execSQL("DELETE FROM recordings WHERE id IN (?, ?)",arrayOf(failed,cancelled))
  }
 }
 @Test fun duplicateRequestsAndQueuedCancellationPreserveTranscript()=runBlocking {
  val instrumentation=InstrumentationRegistry.getInstrumentation()
  val app=instrumentation.targetContext.applicationContext as ReplikaApp
  val dao=app.db.dao();val id="queue-cancel-${System.nanoTime()}"
  val scenario=androidx.test.core.app.ActivityScenario.launch(MainActivity::class.java)
  delay(1000)
  dao.insert(Recording(id,"queue cancellation fixture","absent.wav"))
  val row=SegmentRow.from(id,Segment(id="$id-s",startMs=0,endMs=1000,speakerId=0,text="Сохранённый результат",source="explicit cancellation fixture",edited=true))
  dao.insertSegments(listOf(row))
  val store=ViewModelStore();lateinit var vm: AppViewModel
  instrumentation.runOnMainSync { vm=ViewModelProvider(store,ViewModelProvider.AndroidViewModelFactory.getInstance(app))[AppViewModel::class.java] }
  app.models.gate.lock();var ownGate=true
  try {
   instrumentation.runOnMainSync { vm.process(id,2);vm.process(id,7) }
   withTimeout(10000) { while(dao.recording(id)!!.status!="QUEUED") delay(100) }
   val wm=androidx.work.WorkManager.getInstance(app)
   withTimeout(10000) { while(wm.getWorkInfosForUniqueWork("replika-$id").get().isEmpty()) delay(100) }
   assertEquals(2,dao.recording(id)!!.expectedSpeakers)
   assertEquals(1,wm.getWorkInfosForUniqueWork("replika-$id").get().count { !it.state.isFinished })
   instrumentation.runOnMainSync { vm.cancel(id) }
   withTimeout(10000) { while(dao.recording(id)!!.status!="CANCELLING") delay(100) }
   instrumentation.runOnMainSync { vm.process(id,3) }
   assertEquals("CANCELLING",dao.recording(id)!!.status)
   assertEquals(row,dao.segmentList(id).single())
   app.models.gate.unlock();ownGate=false
   withTimeout(10000) { while(dao.recording(id)!!.status!="CANCELLED") delay(100) }
   assertEquals(row,dao.segmentList(id).single())
  } finally {
   if(ownGate) app.models.gate.unlock()
   instrumentation.runOnMainSync { store.clear() }
   scenario.close()
   dao.recording(id)?.let { dao.status(id,"CANCELLED","Test cleanup") }
   app.db.openHelper.writableDatabase.execSQL("DELETE FROM recordings WHERE id = ?",arrayOf(id))
  }
 }

}

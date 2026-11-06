import android.media.MediaExtractor;
import android.media.MediaFormat;
public final class MediaTrackProbe {
 public static void main(String[] args) throws Exception {
  for(String path:args) {
   MediaExtractor listing=new MediaExtractor();listing.setDataSource(path);
   System.out.println("FILE "+path+" tracks="+listing.getTrackCount());
   for(int i=0;i<listing.getTrackCount();i++) {
    MediaFormat format=listing.getTrackFormat(i);System.out.println("TRACK "+i+" "+format);
    MediaExtractor track=new MediaExtractor();track.setDataSource(path);track.selectTrack(i);
    for(int n=0;n<3;n++) {System.out.println("SAMPLE track="+i+" n="+n+" timeUs="+track.getSampleTime()+" flags="+track.getSampleFlags());if(!track.advance())break;}
    track.release();
   }
   listing.release();
  }
 }
}

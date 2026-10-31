#include <jni.h>
#include <whisper.h>
#include <string>
#include <memory>

extern "C" JNIEXPORT jlong JNICALL
Java_ru_replika_ml_WhisperEngine_init(JNIEnv *env, jobject, jstring path) {
 const char *p=env->GetStringUTFChars(path,nullptr);
 auto params=whisper_context_default_params();params.use_gpu=false;
 auto *ctx=whisper_init_from_file_with_params(p,params);
 env->ReleaseStringUTFChars(path,p);
 return reinterpret_cast<jlong>(ctx);
}
extern "C" JNIEXPORT jstring JNICALL
Java_ru_replika_ml_WhisperEngine_transcribe(JNIEnv *env,jobject,jlong handle,jfloatArray audio) {
 auto *ctx=reinterpret_cast<whisper_context *>(handle);
 const auto n=env->GetArrayLength(audio);
 auto samples=std::make_unique<float[]>(n);
 env->GetFloatArrayRegion(audio,0,n,samples.get());
 auto p=whisper_full_default_params(WHISPER_SAMPLING_GREEDY);
 p.n_threads=2;p.language="ru";p.translate=false;p.no_context=true;
 p.print_realtime=false;p.print_progress=false;p.print_timestamps=false;p.single_segment=true;
 p.suppress_blank=true;
 const int result=whisper_full(ctx,p,samples.get(),n);
 if(result!=0) { env->ThrowNew(env->FindClass("java/lang/IllegalStateException"),"whisper_full failed");return nullptr; }
 std::string text;
 for(int i=0;i<whisper_full_n_segments(ctx);i++) text+=whisper_full_get_segment_text(ctx,i);
 // Return UTF-8 as bytes through Java's UTF-8 decoder: JNI modified UTF-8 cannot encode arbitrary supplementary characters.
 auto bytes=env->NewByteArray(text.size());env->SetByteArrayRegion(bytes,0,text.size(),reinterpret_cast<const jbyte *>(text.data()));
 jclass string=env->FindClass("java/lang/String");jmethodID constructor=env->GetMethodID(string,"<init>","([BLjava/lang/String;)V");
 auto charset=env->NewStringUTF("UTF-8");
 return static_cast<jstring>(env->NewObject(string,constructor,bytes,charset));
}
extern "C" JNIEXPORT void JNICALL
Java_ru_replika_ml_WhisperEngine_free(JNIEnv *,jobject,jlong handle) { whisper_free(reinterpret_cast<whisper_context *>(handle)); }

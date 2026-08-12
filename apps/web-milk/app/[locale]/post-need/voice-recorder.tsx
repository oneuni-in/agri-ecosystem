"use client";

import { Button } from "@agri/ui";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

type RecState = "idle" | "recording" | "recorded" | "denied" | "unsupported";

/**
 * D25 voice-note SHELL: record → play back → attach as a blob. No
 * transcription (Phase 2) and no upload here — the parent form owns the
 * post-then-attach sequence. The icon+field form fully works without this,
 * so unsupported browsers just don't see it (design law: voice first-class,
 * never voice-only).
 */
export function VoiceRecorder({ onBlob }: { onBlob: (blob: Blob | null) => void }) {
  const t = useTranslations("ui.needs");
  const locale = useLocale();
  const [state, setState] = useState<RecState>("idle");
  const [playbackUrl, setPlaybackUrl] = useState<string | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  useEffect(() => {
    if (typeof window !== "undefined" && typeof window.MediaRecorder === "undefined") {
      setState("unsupported");
    }
    return () => {
      if (playbackUrl) URL.revokeObjectURL(playbackUrl);
    };
  }, [playbackUrl]);

  if (state === "unsupported") return null;

  const start = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      // Chrome/Firefox record audio/webm; Safari falls back to audio/mp4 —
      // the backend sniffs magic bytes, so either container is fine.
      const recorder = window.MediaRecorder.isTypeSupported("audio/webm")
        ? new MediaRecorder(stream, { mimeType: "audio/webm" })
        : new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        stream.getTracks().forEach((track) => track.stop());
        onBlob(blob);
        setPlaybackUrl((old) => {
          if (old) URL.revokeObjectURL(old);
          return URL.createObjectURL(blob);
        });
        setState("recorded");
      };
      recorderRef.current = recorder;
      recorder.start();
      setState("recording");
    } catch {
      setState("denied");
    }
  };

  const stop = () => recorderRef.current?.stop();

  const discard = () => {
    onBlob(null);
    setPlaybackUrl((old) => {
      if (old) URL.revokeObjectURL(old);
      return null;
    });
    setState("idle");
  };

  return (
    <div className="space-y-2">
      <p className="text-[13px] font-semibold text-ink">
        {t("voiceLabel")}
        {locale === "en" ? <span className="vern font-normal"> · குரல் குறிப்பு</span> : null}{" "}
        <span className="font-normal text-sub">{t("optional")}</span>
      </p>
      {state === "denied" ? <p className="text-[13px] text-sub">{t("voiceDenied")}</p> : null}
      <div className="flex flex-wrap items-center gap-2">
        {state === "recording" ? (
          <Button
            type="button"
            variant="brand"
            className="max-w-[200px]"
            onClick={stop}
            data-testid="voice-stop"
          >
            {t("voiceStop")}
          </Button>
        ) : (
          <Button
            type="button"
            variant="ghost"
            className="max-w-[240px]"
            onClick={() => void start()}
            data-testid="voice-record"
          >
            {state === "recorded" ? t("voiceReRecord") : t("voiceRecord")}
            {locale === "en" ? <span className="vern"> · பேசுங்கள்</span> : null}
          </Button>
        )}
        {state === "recorded" && playbackUrl ? (
          <>
            <audio controls src={playbackUrl} className="h-11 max-w-full" />
            <Button
              type="button"
              variant="ghost"
              className="max-w-[120px]"
              onClick={discard}
              data-testid="voice-discard"
            >
              {t("voiceRemove")}
            </Button>
          </>
        ) : null}
      </div>
    </div>
  );
}

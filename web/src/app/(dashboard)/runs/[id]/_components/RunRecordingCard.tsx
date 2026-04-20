"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";

interface RunRecordingCardProps {
  recordingS3Key?: string | null;
  recordingUrl: string | null;
  recordingError: string;
  recordingLoading: boolean;
  onLoad: () => void;
  onTimeUpdate?: (currentTimeMs: number) => void;
}

const CANVAS_HEIGHT = 80;
const HARNESS_COLOR = "#3b82f6";
const BOT_COLOR = "#6b7280";

function drawWaveform(
  canvas: HTMLCanvasElement,
  audioBuffer: AudioBuffer,
  currentTimeSec: number,
) {
  const rect = canvas.getBoundingClientRect();
  const logicalWidth = Math.round(rect.width) || canvas.width || 300;
  canvas.width = logicalWidth;
  canvas.height = CANVAS_HEIGHT;

  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  const w = logicalWidth;
  const h = CANVAS_HEIGHT;
  const midY = h / 2;
  const isStereo = audioBuffer.numberOfChannels >= 2;
  const ch0 = audioBuffer.getChannelData(0);
  const ch1 = isStereo ? audioBuffer.getChannelData(1) : null;
  const totalSamples = audioBuffer.length;
  const samplesPerPixel = totalSamples / w;

  ctx.clearRect(0, 0, w, h);

  if (isStereo) {
    // L channel (harness) — peaks drawn above center
    ctx.fillStyle = HARNESS_COLOR;
    for (let x = 0; x < w; x++) {
      const s = Math.floor(x * samplesPerPixel);
      const e = Math.min(Math.floor((x + 1) * samplesPerPixel), totalSamples);
      let peak = 0;
      for (let i = s; i < e; i++) {
        const a = Math.abs(ch0[i]);
        if (a > peak) peak = a;
      }
      const barH = peak * midY * 0.92;
      ctx.fillRect(x, midY - barH, 1, barH);
    }

    // R channel (bot) — peaks drawn below center
    ctx.fillStyle = BOT_COLOR;
    for (let x = 0; x < w; x++) {
      const s = Math.floor(x * samplesPerPixel);
      const e = Math.min(Math.floor((x + 1) * samplesPerPixel), totalSamples);
      let peak = 0;
      for (let i = s; i < e; i++) {
        const a = Math.abs(ch1![i]);
        if (a > peak) peak = a;
      }
      const barH = peak * midY * 0.92;
      ctx.fillRect(x, midY, 1, barH);
    }
  } else {
    // Mono — full height centered
    ctx.fillStyle = BOT_COLOR;
    for (let x = 0; x < w; x++) {
      const s = Math.floor(x * samplesPerPixel);
      const e = Math.min(Math.floor((x + 1) * samplesPerPixel), totalSamples);
      let peak = 0;
      for (let i = s; i < e; i++) {
        const a = Math.abs(ch0[i]);
        if (a > peak) peak = a;
      }
      const barH = peak * midY * 0.92;
      ctx.fillRect(x, midY - barH, 1, barH * 2);
    }
  }

  // Center divider line
  ctx.strokeStyle = "rgba(255,255,255,0.07)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(0, midY);
  ctx.lineTo(w, midY);
  ctx.stroke();

  // Playhead
  if (audioBuffer.duration > 0 && currentTimeSec > 0) {
    const x = Math.round((currentTimeSec / audioBuffer.duration) * w);
    ctx.strokeStyle = "rgba(255,255,255,0.85)";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, h);
    ctx.stroke();
  }
}

function formatTime(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function RunRecordingCard({
  recordingS3Key,
  recordingUrl,
  recordingError,
  recordingLoading,
  onLoad,
  onTimeUpdate,
}: RunRecordingCardProps) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [audioBuffer, setAudioBuffer] = useState<AudioBuffer | null>(null);
  const [waveformLoading, setWaveformLoading] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTimeSec, setCurrentTimeSec] = useState(0);
  const [duration, setDuration] = useState(0);

  const isStereo = audioBuffer ? audioBuffer.numberOfChannels >= 2 : false;

  // Decode audio for waveform whenever a new URL is loaded
  useEffect(() => {
    if (!recordingUrl) {
      setAudioBuffer(null);
      setCurrentTimeSec(0);
      setDuration(0);
      return;
    }
    let cancelled = false;
    setWaveformLoading(true);
    void (async () => {
      try {
        const resp = await fetch(recordingUrl);
        const arrayBuffer = await resp.arrayBuffer();
        if (cancelled) return;
        const audioCtx = new AudioContext();
        const decoded = await audioCtx.decodeAudioData(arrayBuffer);
        if (cancelled) return;
        setAudioBuffer(decoded);
        await audioCtx.close();
      } catch {
        // Waveform decode failed — native audio playback still works
      } finally {
        if (!cancelled) setWaveformLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [recordingUrl]);

  const redraw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || !audioBuffer) return;
    drawWaveform(canvas, audioBuffer, currentTimeSec);
  }, [audioBuffer, currentTimeSec]);

  useEffect(() => {
    redraw();
  }, [redraw]);

  // Redraw when the container is resized
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ro = new ResizeObserver(() => redraw());
    ro.observe(canvas);
    return () => ro.disconnect();
  }, [redraw]);

  function handleTimeUpdate() {
    const audio = audioRef.current;
    if (!audio) return;
    const t = audio.currentTime;
    setCurrentTimeSec(t);
    onTimeUpdate?.(t * 1000);
  }

  function handleLoadedMetadata() {
    const audio = audioRef.current;
    if (audio) setDuration(audio.duration);
  }

  function togglePlayPause() {
    const audio = audioRef.current;
    if (!audio) return;
    if (isPlaying) {
      audio.pause();
    } else {
      void audio.play();
    }
  }

  function handleCanvasClick(e: React.MouseEvent<HTMLCanvasElement>) {
    const audio = audioRef.current;
    const canvas = canvasRef.current;
    if (!audio || !canvas) return;
    const rect = canvas.getBoundingClientRect();
    const ratio = (e.clientX - rect.left) / rect.width;
    const dur = audioBuffer?.duration ?? audio.duration;
    if (dur > 0) {
      audio.currentTime = ratio * dur;
    }
  }

  if (!recordingS3Key) {
    return null;
  }

  return (
    <section>
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-text-secondary">
        Call Recording
      </h2>
      <Card>
        <CardBody className="space-y-3">
          <p className="break-all font-mono text-xs text-text-muted">{recordingS3Key}</p>

          {!recordingUrl ? (
            <div className="flex items-center gap-2">
              <Button variant="secondary" size="sm" onClick={onLoad} disabled={recordingLoading}>
                {recordingLoading ? "Loading…" : "Load Recording"}
              </Button>
              {recordingError ? <p className="text-xs text-fail">{recordingError}</p> : null}
            </div>
          ) : (
            <div className="space-y-2">
              {/* Waveform canvas */}
              <div
                className="relative rounded-md overflow-hidden border border-border bg-bg-elevated"
                style={{ height: CANVAS_HEIGHT }}
              >
                {waveformLoading && (
                  <div className="absolute inset-0 flex items-center justify-center">
                    <span className="text-xs text-text-muted">Drawing waveform…</span>
                  </div>
                )}
                {isStereo && !waveformLoading && (
                  <div className="absolute top-1 left-2 flex gap-3 pointer-events-none z-10">
                    <span className="text-[10px] font-mono" style={{ color: HARNESS_COLOR }}>
                      ▲ harness
                    </span>
                    <span className="text-[10px] font-mono" style={{ color: BOT_COLOR }}>
                      ▼ bot
                    </span>
                  </div>
                )}
                <canvas
                  ref={canvasRef}
                  height={CANVAS_HEIGHT}
                  className="w-full cursor-pointer block absolute inset-0"
                  onClick={handleCanvasClick}
                />
              </div>

              {/* Playback controls */}
              <div className="flex items-center gap-3">
                <Button variant="secondary" size="sm" onClick={togglePlayPause}>
                  {isPlaying ? "Pause" : "Play"}
                </Button>
                <span className="font-mono text-xs text-text-muted">
                  {formatTime(currentTimeSec)}{" "}
                  {(audioBuffer?.duration ?? duration) > 0
                    ? `/ ${formatTime(audioBuffer?.duration ?? duration)}`
                    : ""}
                </span>
                <Button
                  variant="secondary"
                  size="sm"
                  className="ml-auto"
                  onClick={onLoad}
                  disabled={recordingLoading}
                >
                  {recordingLoading ? "Loading…" : "Refresh"}
                </Button>
              </div>

              {/* Hidden native audio element handles actual playback */}
              <audio
                ref={audioRef}
                src={recordingUrl}
                preload="metadata"
                className="hidden"
                onTimeUpdate={handleTimeUpdate}
                onLoadedMetadata={handleLoadedMetadata}
                onPlay={() => setIsPlaying(true)}
                onPause={() => setIsPlaying(false)}
                onEnded={() => setIsPlaying(false)}
              />
            </div>
          )}
        </CardBody>
      </Card>
    </section>
  );
}

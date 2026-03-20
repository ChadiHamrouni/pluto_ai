/**
 * useTTS — pipelined sentence-level TTS playback.
 *
 * Uses POST /tts/sentences which streams one length-prefixed WAV blob per
 * sentence.  Protocol: [4-byte uint32 LE length][WAV bytes].
 *
 * Playback pipeline:
 *  - Sentence 1 starts playing as soon as it's received (~300ms)
 *  - While sentence N plays, sentence N+1 is decoded and queued
 *  - Sentences play back-to-back with no gap
 *
 * Usage:
 *   const { speaking, speak, stop } = useTTS();
 *   speak("Hello world. How are you?", { onDone: () => startListening() });
 *   stop();  // interrupts immediately
 */

import { useRef, useState, useCallback } from "react";
import { ttsStreamSentences } from "../api";

export function useTTS() {
  const [speaking, setSpeaking] = useState(false);

  const abortRef   = useRef(null);   // AbortController for the fetch
  const ctxRef     = useRef(null);   // AudioContext
  const queueRef   = useRef([]);     // decoded AudioBuffers waiting to play
  const playingRef = useRef(false);  // true while a source is active
  const doneRef    = useRef(false);  // true when all sentences have been fetched
  const onDoneRef  = useRef(null);   // callback to fire when all sentences played

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    onDoneRef.current = null;
    queueRef.current = [];
    playingRef.current = false;
    doneRef.current = false;

    try { ctxRef.current?.close(); } catch {}
    ctxRef.current = null;

    setSpeaking(false);
  }, []);

  // Play the next queued AudioBuffer, scheduling the one after it in parallel.
  function _playNext() {
    const ctx = ctxRef.current;
    if (!ctx || abortRef.current?.signal.aborted) return;

    if (queueRef.current.length === 0) {
      // Nothing ready yet — if fetching is done there's nothing left
      if (doneRef.current) {
        playingRef.current = false;
        setSpeaking(false);
        onDoneRef.current?.();
        onDoneRef.current = null;
      }
      // else: a new buffer will arrive and call _playNext again
      return;
    }

    const buffer = queueRef.current.shift();
    playingRef.current = true;

    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);
    source.onended = () => {
      if (abortRef.current?.signal.aborted) return;
      _playNext();
    };
    source.start();
  }

  const speak = useCallback(async (text, { onDone } = {}) => {
    if (!text?.trim()) return;

    stop();

    const ac = new AudioContext();
    ctxRef.current  = ac;
    const abort = new AbortController();
    abortRef.current = abort;
    onDoneRef.current = onDone ?? null;
    queueRef.current  = [];
    playingRef.current = false;
    doneRef.current   = false;
    setSpeaking(true);

    try {
      const response = await ttsStreamSentences(text, abort.signal);
      if (!response.ok) {
        console.error("[useTTS] endpoint error:", response.status);
        setSpeaking(false);
        return;
      }

      const reader = response.body.getReader();
      let leftover = new Uint8Array(0); // bytes not yet consumed

      const readExact = async (n) => {
        // Read exactly n bytes from the stream, buffering leftovers.
        const result = new Uint8Array(n);
        let filled = 0;

        // Drain leftover first
        if (leftover.length > 0) {
          const take = Math.min(leftover.length, n);
          result.set(leftover.subarray(0, take), 0);
          leftover = leftover.subarray(take);
          filled += take;
        }

        while (filled < n) {
          const { done, value } = await reader.read();
          if (abort.signal.aborted) return null;
          if (done) return filled > 0 ? result.subarray(0, filled) : null;
          const need = n - filled;
          if (value.length <= need) {
            result.set(value, filled);
            filled += value.length;
          } else {
            result.set(value.subarray(0, need), filled);
            leftover = value.subarray(need);
            filled += need;
          }
        }
        return result;
      };

      // Read sentences one by one
      while (true) {
        if (abort.signal.aborted) return;

        // Read 4-byte length prefix
        const lenBytes = await readExact(4);
        if (!lenBytes || lenBytes.length < 4) break;

        const wavLen = new DataView(lenBytes.buffer, lenBytes.byteOffset, 4).getUint32(0, true);
        if (wavLen === 0) continue;

        const wavBytes = await readExact(wavLen);
        if (!wavBytes || abort.signal.aborted) return;

        // Decode this sentence's WAV and enqueue it
        try {
          const decoded = await ac.decodeAudioData(wavBytes.buffer.slice(wavBytes.byteOffset, wavBytes.byteOffset + wavBytes.byteLength));
          if (abort.signal.aborted) return;
          queueRef.current.push(decoded);

          // Start playback as soon as the first sentence is ready
          if (!playingRef.current) _playNext();
        } catch (decodeErr) {
          console.warn("[useTTS] decode error for sentence:", decodeErr);
        }
      }

      doneRef.current = true;
      // If player already finished before we set doneRef, fire onDone now
      if (!playingRef.current && queueRef.current.length === 0) {
        setSpeaking(false);
        onDoneRef.current?.();
        onDoneRef.current = null;
      }

    } catch (e) {
      if (e.name !== "AbortError") console.error("[useTTS] error:", e);
      setSpeaking(false);
    }
  }, [stop]);

  return { speaking, speak, stop };
}

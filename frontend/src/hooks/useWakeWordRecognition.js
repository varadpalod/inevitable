import { useEffect, useRef } from 'react';

/**
 * Custom hook for persistent, continuous wake-word detection using Web Speech API.
 * 
 * Key guarantees:
 * 1. Single persistent SpeechRecognition instance in recognitionRef.
 * 2. Live ref state (listeningRef, isProcessingRef, isStartingRef, isStartedRef, isAbortedRef).
 * 3. Event handlers attached ONCE when SpeechRecognition object is instantiated.
 * 4. Prevents InvalidStateError or duplicate start calls via isStartingRef & isStartedRef flags.
 * 5. Handles 'aborted' events cleanly without infinite retry loops.
 * 6. Detailed lifecycle logs (START, END, AUDIO START/END, SPEECH START/END, ERROR).
 */
export function useWakeWordRecognition({
  enabled = true,
  isWakeWordListening = true,
  onWakeWordDetected,
  onTranscript,
  onError,
  onStart
}) {
  const recognitionRef = useRef(null);
  const listeningRef = useRef(isWakeWordListening);
  const isProcessingRef = useRef(false);
  const isStartingRef = useRef(false);
  const isStartedRef = useRef(false);
  const isAbortedRef = useRef(false);
  const restartTimerRef = useRef(null);

  // Store current callback references in refs so handlers don't need re-binding
  const onWakeWordDetectedRef = useRef(onWakeWordDetected);
  const onTranscriptRef = useRef(onTranscript);
  const onErrorRef = useRef(onError);
  const onStartRef = useRef(onStart);

  useEffect(() => {
    onWakeWordDetectedRef.current = onWakeWordDetected;
  }, [onWakeWordDetected]);

  useEffect(() => {
    onTranscriptRef.current = onTranscript;
  }, [onTranscript]);

  useEffect(() => {
    onErrorRef.current = onError;
  }, [onError]);

  useEffect(() => {
    onStartRef.current = onStart;
  }, [onStart]);

  const safeStart = () => {
    if (!listeningRef.current || isProcessingRef.current) return;
    if (isStartingRef.current || isStartedRef.current) {
      console.log("[useWakeWordRecognition] Already starting or running, skipping start()");
      return;
    }
    if (!recognitionRef.current) return;

    try {
      isStartingRef.current = true;
      recognitionRef.current.start();
    } catch (err) {
      isStartingRef.current = false;
      console.warn("[useWakeWordRecognition] safeStart exception:", err);
      if (err.name === 'InvalidStateError') {
        isStartedRef.current = true;
      } else if (listeningRef.current && !isProcessingRef.current) {
        clearTimeout(restartTimerRef.current);
        restartTimerRef.current = setTimeout(safeStart, 1500);
      }
    }
  };

  const safeStop = () => {
    clearTimeout(restartTimerRef.current);
    isAbortedRef.current = true;
    if (recognitionRef.current && (isStartedRef.current || isStartingRef.current)) {
      try {
        recognitionRef.current.abort();
      } catch (err) {
        console.warn("[useWakeWordRecognition] safeStop exception:", err);
      }
    }
    isStartingRef.current = false;
    isStartedRef.current = false;
  };

  // Keep listeningRef in sync with isWakeWordListening state
  useEffect(() => {
    listeningRef.current = isWakeWordListening;
    if (isWakeWordListening) {
      isProcessingRef.current = false;
      isAbortedRef.current = false;
      safeStart();
    } else {
      safeStop();
    }
  }, [isWakeWordListening]);

  // Main lifecycle effect for initialization and handler registration
  useEffect(() => {
    if (!enabled) return;

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      if (onErrorRef.current) {
        onErrorRef.current('not-supported');
      }
      return;
    }

    // Attach handlers ONCE when creating the recognition object
    if (!recognitionRef.current) {
      const rec = new SpeechRecognition();
      rec.continuous = true;
      rec.interimResults = true;
      rec.lang = 'en-US';

      rec.onstart = () => {
        console.log("START");
        isStartingRef.current = false;
        isStartedRef.current = true;
        if (onStartRef.current) onStartRef.current();
      };

      rec.onend = () => {
        console.log("END");
        isStartingRef.current = false;
        isStartedRef.current = false;

        const shouldRestart = listeningRef.current && !isProcessingRef.current && !isAbortedRef.current;
        isAbortedRef.current = false;

        if (shouldRestart) {
          clearTimeout(restartTimerRef.current);
          restartTimerRef.current = setTimeout(() => {
            safeStart();
          }, 300);
        }
      };

      rec.onaudiostart = () => console.log("AUDIO START");
      rec.onaudioend = () => console.log("AUDIO END");
      rec.onspeechstart = () => console.log("SPEECH START");
      rec.onspeechend = () => console.log("SPEECH END");

      rec.onerror = (e) => {
        console.log("ERROR", e.error);
        if (e.error === 'not-allowed') {
          if (onErrorRef.current) onErrorRef.current('not-allowed');
        } else if (e.error === 'aborted') {
          isAbortedRef.current = true;
        }

        if (e.error !== 'aborted' && listeningRef.current && !isProcessingRef.current) {
          clearTimeout(restartTimerRef.current);
          restartTimerRef.current = setTimeout(() => {
            safeStart();
          }, 1000);
        }
      };

      rec.onresult = (event) => {
        if (!listeningRef.current || isProcessingRef.current) return;

        for (let i = event.resultIndex; i < event.results.length; i++) {
          const transcriptChunk = event.results[i][0].transcript.trim();
          const lowerChunk = transcriptChunk.toLowerCase();

          if (onTranscriptRef.current) {
            onTranscriptRef.current(transcriptChunk);
          }

          // Broad phonetic matching for 'JARVIS' across browser STT engines
          const wakeWordRegex = /(jarvis|hey jarvis|hello jarvis|hi jarvis|javis|travis|stark|yavis|charvis|service)/i;

          if (wakeWordRegex.test(lowerChunk) && !isProcessingRef.current) {
            isProcessingRef.current = true;
            try {
              rec.stop();
            } catch (e) {}
            if (onWakeWordDetectedRef.current) {
              onWakeWordDetectedRef.current(transcriptChunk);
            }
            break;
          }
        }
      };

      recognitionRef.current = rec;
    }

    // Initial start if listening
    if (listeningRef.current) {
      safeStart();
    }

    return () => {
      clearTimeout(restartTimerRef.current);
      if (recognitionRef.current) {
        isAbortedRef.current = true;
        try {
          recognitionRef.current.abort();
        } catch (e) {}
        isStartingRef.current = false;
        isStartedRef.current = false;
      }
    };
  }, [enabled]);

  return {
    start: safeStart,
    stop: safeStop,
    recognition: recognitionRef.current
  };
}

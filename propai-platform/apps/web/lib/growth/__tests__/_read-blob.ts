/**
 * 테스트 공용 — `Blob` 을 텍스트로 읽는다.
 *
 * ★**왜 공용인가**(2026-08-28): jsdom 에서 Blob 을 읽는 방법 중 하나는 **던지지 않고 틀린 답**을 준다.
 * 그것으로 단언을 짜면 **통과하지만 아무것도 안 재는 테스트**가 된다. 다음 사람이 그 함정에
 * 빠지지 않도록 **옳은 방법 하나만** 여기 둔다.
 *
 *     blob.text / arrayBuffer / stream   → **undefined**(jsdom Blob 은 최소 구현)
 *     new Response(blob).text()          → **"[object Blob]"**  ★조용히 틀린 답
 *     FileReader.readAsText(blob)        → **{"a":1}**          ◎ 유일하게 옳다
 *
 * ★그리고 읽은 결과가 **실제 JSON 인지**까지 확인한다 — 조용히 틀린 답을 초록으로 넘기지 않는다.
 */
export async function readBlobAsJsonText(blob: Blob): Promise<string> {
  const text = await new Promise<string>((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result));
    r.onerror = () => reject(r.error ?? new Error("FileReader 실패"));
    r.readAsText(blob);
  });
  try {
    JSON.parse(text);
  } catch {
    throw new Error(
      `Blob 을 읽었는데 JSON 이 아니다 — **읽기 방법** 또는 **본문 포맷**을 확인하라: ${text.slice(0, 80)}`,
    );
  }
  return text;
}

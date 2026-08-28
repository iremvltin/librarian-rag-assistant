"""
rag_engine.py
Performs cosine similarity search on assistant.db and generates responses 
by providing context to Qwen.

Intent separation (recommendation vs. specific book query) is handled via prompts/heuristics:
- Specific book query (exact title match): The LLM receives ONLY that book's summary.
- Recommendation query: The LLM receives the top-K candidate books, picks the most suitable ones, and is asked to explain why.
- Small talk (greetings, how-are-yous, etc.): Returns a short conversational response adopting a librarian persona without performing a search.
- Unknown/not-in-library books or off-topic questions: Explicitly answers with "I don't know" instead of hallucinating an answer.
"""

import difflib
import re
import sqlite3
from pathlib import Path

import numpy as np
from openai import OpenAI

from foundry_utils import ensure_model_loaded, get_client, resolve_model_id

DB_PATH = Path("assistant.db")
EMBEDDING_MODEL_ALIAS = "qwen3-embedding-0.6b"
CHAT_MODEL_ALIAS = "qwen2.5-1.5b"
TOP_K = 3
EXACT_MATCH_THRESHOLD = 2.0  # search() eşleşmesi
LOW_CONFIDENCE_THRESHOLD = 0.2  # "anlayamadim"
OFF_TOPIC_THRESHOLD = 0.42  # "bilmiyorum"

RECOMMENDATION_KEYWORDS = (
    "oner", "öner", "tavsiye", "benzer", "gibi kitap", "gibi bir kitap",
    "recommend", "similar", "suggest",
)


SPECIFIC_BOOK_INTENT_KEYWORDS = (
    "konusu", "özeti", "ozeti", "hakkında bilgi", "hakkinda bilgi",
    "kimin eseri", "ne anlatıyor", "ne anlatiyor", "içeriği", "icerigi",
    "hakkında", "hakkinda",
)


SMALL_TALK_KEYWORDS = (
    "selam", "selamlar", "merhaba", "merhabalar", "naber", "napıyorsun",
    "napiyorsun", "ne yapıyorsun", "ne yapiyorsun", "nasılsın", "nasilsin",
    "nasılsınız", "nasilsiniz", "iyi misin", "iyi misiniz", "günaydın",
    "gunaydin", "iyi akşamlar", "iyi aksamlar", "iyi geceler", "hoşça kal",
    "hosca kal", "hoşçakal", "hoscakal", "görüşürüz", "gorusuruz",
    "teşekkür", "tesekkur", "teşekkürler", "tesekkurler", "sağol", "sagol",
    "sağ ol", "sag ol", "kimsin", "sen kimsin", "adın ne", "adin ne",
    "kimsin sen", "ne haber",
)

THINK_TAG_PATTERN = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _strip_think_tags(text: str) -> str:
    """
    <think>/</think> ETIKETLERINI kaldirir ama icindeki metni SILMEZ.
    Bazi durumlarda model asil cevabi (kapanmamis) think blogunun icine
    yaziyor; bloguu tamamen atarsak asil cevabi kaybederiz.
    """
    return text.replace("<think>", "").replace("</think>", "").strip()


LEAK_MARKERS = ("\n---", "**Yazar:", "\nYazar:", "Verilen metin")


def _cut_at_leak_markers(text: str) -> str:
    """Modelin promptu/sablonu geri kusmaya basladigi noktadan itibaren keser."""
    cut_at = len(text)
    for marker in LEAK_MARKERS:
        idx = text.find(marker)
        if idx > 20:  
            cut_at = min(cut_at, idx)
    return text[:cut_at].strip()


def _truncate_repetition(text: str) -> str:
    """Kucuk modellerde gorulen dongu/tekrar sorununa karsi guvenlik agi."""
    loop_match = re.search(r"(.{8,80}?)(\1){2,}", text, re.DOTALL)
    if loop_match:
        text = text[: loop_match.start()]

    sentences = re.split(r"(?<=[.!?])\s+", text)
    seen = set()
    kept = []
    for sentence in sentences:
        key = sentence.strip()
        if key and key in seen:
            break
        if key:
            seen.add(key)
        kept.append(sentence)
    return " ".join(kept).strip()


def _looks_like_small_talk(query_lower: str) -> bool:
    """Selamlasma / hal hatir sorma / tesekkur gibi kitap aramayla ilgisi
    olmayan kisa mesajlari yakalar."""
    word_count = len(query_lower.split())
    if word_count == 0 or word_count > 6:
        return False
    return any(kw in query_lower for kw in SMALL_TALK_KEYWORDS)


SMALL_TALK_SYSTEM_PROMPT = (
    "Dusunme adimlarini gösterme, <think> etiketi kullanma, dogrudan cevapla.\n\n"
    "Sen bu uygulamada calisan, kitap oneren ve istenen kitabin konusunu "
    "anlatan bir kutuphanecisin. Kullanici su an sana sadece selam veriyor, "
    "hal hatir soruyor ya da tesekkur ediyor; kitapla ilgili bir istek yok.\n"
    "Gorevin: sicak, kisa (1-2 cumle) ve dogal bir Turkce cevap vermek. "
    "Kendini bir kutuphaneci olarak tanit veya oyle davran, ve istersen "
    "kullaniciya istedigi zaman bir kitap onerebilecegini ya da bildigi bir "
    "kitabin konusunu anlatabilecegini kisaca hatirlat. Uzun aciklama yapma, "
    "kitap listesi uydurma, sadece sohbet et."
)

SYSTEM_PROMPT = (
    "Dusunme adimlarini gösterme, <think> etiketi kullanma, dogrudan cevapla.\n\n"
    "Sana bir KITAP LISTESI ve kullanicinin bir ISTEGI verilecek. Gorevin: "
    "listeden kullanicinin istegine EN UYGUN 1-2 kitabi secmek ve neden uygun "
    "olduklarini 2-3 kisa cumleyle aciklamak. Baska hicbir sey yazma.\n\n"
    "ORNEK:\n"
    "KITAP LISTESI:\n"
    "- Ruzgarin Golgesi | Tur: Gizem, Tarihi Kurgu\n"
    "  Ozet: Bir genc, gizemli bir kitapla ilgili karanlik bir sirri cozmeye calisir.\n"
    "- Yuzuklerin Efendisi | Tur: Epik Fantastik\n"
    "  Ozet: Bir grup kahraman, dunyayi tehdit eden kotu bir gucu yok etmek icin yola cikar.\n"
    "ISTEK: gizemli, atmosferik bir kitap oner\n\n"
    "CEVAP: Sana 'Ruzgarin Golgesi'ni oneririm. Karanlik bir sirri cozmeye "
    "calisan bir genci konu alan, atmosferik ve gizemli bir hikayesi var. "
    "Tam aradigin turden bir kitap.\n\n"
    "Simdi ASAGIDAKI gercek kitap listesini ve kullanicinin istegini kullanarak "
    "AYNI KISALIKTA (2-3 cumle) bir cevap ver. Listede olmayan kitap ya da "
    "bilgi uydurma; sadece verilen ozetlerdeki bilgileri kullan."
)

SPECIFIC_BOOK_SYSTEM_PROMPT = (
    "Dusunme adimlarini gösterme, <think> etiketi kullanma, dogrudan cevapla.\n\n"
    "Sana tek bir kitabin basligi ve spoiler-free ozeti verilecek.\n"
    "Gorevin: SADECE bu ozeti daha akici, dogal bir Turkce ile yeniden ifade "
    "etmek. Ozette GECMEYEN hicbir yeni bilgi, karakter, olay, mekan ya da "
    "detay EKLEME. Hicbir seyi yorumlama ya da degistirme, sadece verilen "
    "metni ayni anlami koruyarak kendi cumlelerinle yeniden yaz.\n"
    "Yazar adini, turu, sayfa sayisini tekrar etme; dogrudan hikayeye gir."
)


class RagEngine:
    def __init__(self) -> None:
        ensure_model_loaded(EMBEDDING_MODEL_ALIAS)
        ensure_model_loaded(CHAT_MODEL_ALIAS)

        client = get_client()
        self._embed_client = client
        self._chat_client = client
        self._embed_model_id = resolve_model_id(client, EMBEDDING_MODEL_ALIAS)
        self._chat_model_id = resolve_model_id(client, CHAT_MODEL_ALIAS)

        self.books: list[dict] = []
        self.embeddings = np.empty((0, 0), dtype=np.float32)
        self._norm_embeddings = np.empty((0, 0), dtype=np.float32)
        self.broad_genres: list[str] = []
        self.last_matched_genre: str | None = None
        self._load_books()

    # ------------------------------------------------------------------ #
    # Veri yukleme
    # ------------------------------------------------------------------ #
    def _load_books(self) -> None:
        if not DB_PATH.exists():
            raise FileNotFoundError(
                f"{DB_PATH} bulunamadi. Once ingest.py'yi calistir."
            )

        conn = sqlite3.connect(DB_PATH)
        cur = conn.execute(
            """
            SELECT id, title_tr, title_en, author, genre, broad_genre, page, summary, embedding
            FROM books
            WHERE embedding IS NOT NULL
            """
        )

        books, vectors = [], []
        for row in cur.fetchall():
            books.append(
                {
                    "id": row[0],
                    "title_tr": row[1],
                    "title_en": row[2],
                    "author": row[3],
                    "genre": row[4],
                    "broad_genre": row[5],
                    "page": row[6],
                    "summary": row[7],
                }
            )
            vectors.append(np.frombuffer(row[8], dtype=np.float32))
        conn.close()

        self.books = books
        self.broad_genres = sorted({b["broad_genre"] for b in books if b.get("broad_genre")})
        if vectors:
            self.embeddings = np.vstack(vectors)
            norms = np.linalg.norm(self.embeddings, axis=1, keepdims=True)
            norms[norms == 0] = 1e-8
            self._norm_embeddings = self.embeddings / norms
        else:
            self.embeddings = np.empty((0, 0), dtype=np.float32)
            self._norm_embeddings = np.empty((0, 0), dtype=np.float32)


    # SEARCH
   
    def embed_query(self, text: str) -> np.ndarray:
        resp = self._embed_client.embeddings.create(
            model=self._embed_model_id, input=text
        )
        vec = np.array(resp.data[0].embedding, dtype=np.float32)
        return vec / (np.linalg.norm(vec) + 1e-8)

    def _match_genre(self, query_lower: str, fuzzy_cutoff: float = 0.75) -> str | None:
        """Sorguda bir broad_genre adi geciyor mu kontrol eder.
        Once tam alt-dize eslesmesi, olmazsa yazim hatalarina toleransli
        bulanik (fuzzy) eslesme dener (ornegin 'bulum kurgu' -> 'Bilim Kurgu')."""
        for genre in self.broad_genres:
            if genre and genre.lower() in query_lower:
                return genre

        words = query_lower.split()
        grams = set(words)
        for i in range(len(words) - 1):
            grams.add(f"{words[i]} {words[i + 1]}")

        genre_lower_map = {g.lower(): g for g in self.broad_genres if g}
        for gram in grams:
            match = difflib.get_close_matches(
                gram, genre_lower_map.keys(), n=1, cutoff=fuzzy_cutoff
            )
            if match:
                return genre_lower_map[match[0]]
        return None

    def search(
        self,
        query: str,
        top_k: int = TOP_K,
        exclude_ids: set | None = None,
        force_genre: str | None = None,
    ) -> list[tuple[dict, float]]:
        if len(self.books) == 0:
            self.last_matched_genre = None
            return []

        query_lower = query.lower()
        q = self.embed_query(query)
        sims = self._norm_embeddings @ q

        for i, book in enumerate(self.books):
            for title_field in ("title_tr", "title_en"):
                title = (book.get(title_field) or "").strip().lower()
                if title and len(title) >= 3 and title in query_lower:
                    sims[i] = max(sims[i], 1.0) + 1.0  # kesin oncelik
                    break

        matched_genre = self._match_genre(query_lower) or force_genre
        self.last_matched_genre = matched_genre

        if matched_genre:
            in_genre = {
                i for i, b in enumerate(self.books) if b.get("broad_genre") == matched_genre
            }
            exact_matches = {i for i in range(len(self.books)) if sims[i] >= EXACT_MATCH_THRESHOLD}
            allowed = in_genre | exact_matches
            if allowed:
                sims = np.where(np.isin(np.arange(len(self.books)), list(allowed)), sims, -np.inf)

        if exclude_ids:
            for i, book in enumerate(self.books):
                if book["id"] in exclude_ids and sims[i] < EXACT_MATCH_THRESHOLD:
                    sims[i] = -np.inf

        idx = np.argsort(-sims)[:top_k]
        return [(self.books[i], float(sims[i])) for i in idx]

    # ANSWER 
   
    @staticmethod
    def _format_context(results: list[tuple[dict, float]]) -> str:
        lines = []
        for book, _score in results:
            lines.append(
                f"- {book['title_tr']} ({book['title_en']}) | Yazar: {book['author']} | "
                f"Tur: {book['genre']} / {book['broad_genre']} | Sayfa: {book['page']}\n"
                f"  Ozet: {book['summary'] or 'ozet mevcut degil'}"
            )
        return "\n".join(lines)

    def _answer_small_talk(self, query: str):
        """Selamlasma / hal hatir sorma gibi mesajlara, kitap aramaya
        girmeden kutuphaneci kimligiyle kisa bir sohbet cevabi uretir."""
        completion = self._chat_client.chat.completions.create(
            model=self._chat_model_id,
            messages=[
                {"role": "system", "content": SMALL_TALK_SYSTEM_PROMPT},
                {"role": "user", "content": f"{query}\n\n/no_think"},
            ],
            temperature=0.6,
            max_tokens=200,
        )
        raw = completion.choices[0].message.content or ""
        cleaned = _truncate_repetition(_cut_at_leak_markers(_strip_think_tags(raw)))
        if len(cleaned) < 3:
            cleaned = (
                "Selam! Ben senin kütüphanecinim. İstersen sana bir kitap "
                "önerebilirim ya da bildiğin bir kitabın konusunu anlatabilirim."
            )
        return cleaned, []

    def answer(
        self,
        query: str,
        top_k: int = TOP_K,
        exclude_ids: set | None = None,
        force_genre: str | None = None,
    ):
        query_lower = query.lower().strip()

        # Kitap arama/oneri niyeti tasimayan, sadece selamlasma/hal hatir/
        # tesekkur gibi kisa sohbet mesajlarini once burada yakalayip
        # aramaya hic girmeden cevapliyoruz.
        if _looks_like_small_talk(query_lower):
            return self._answer_small_talk(query)

        results = self.search(
            query, top_k=top_k, exclude_ids=exclude_ids, force_genre=force_genre
        )

        # Hicbir sonuc yoksa ya da en iyi eslesme bile cok zayifsa (muhtemelen
        # yazim hatali sorgu), uydurma bir cevap vermek yerine
        # tekrar sormasini istemek
        if not results or results[0][1] < LOW_CONFIDENCE_THRESHOLD:
            return "Anlayamadım, tekrar sorar mısın lütfen?", results

        looks_like_recommendation = any(kw in query_lower for kw in RECOMMENDATION_KEYWORDS)
        looks_like_specific_book = any(kw in query_lower for kw in SPECIFIC_BOOK_INTENT_KEYWORDS)
        top_score = results[0][1]

        # Kullanici acikca belirli bir kitap hakkinda bilgi istiyor
        # (oneri degil) ama kesin baslik eslesmesi bulunamadi: bu kitap
        # kutuphanede yok demektir. Rastgele bir kitabi anlatmak
        # yerine acikca "bilmiyorum" de.
        if looks_like_specific_book and not looks_like_recommendation and top_score < EXACT_MATCH_THRESHOLD:
            return (
                "Bu kitap kütüphanemde yok, bu yüzden hakkında bilgi veremiyorum. "
                "Bilmiyorum. Başka bir kitap sorabilir ya da tür bazlı bir öneri "
                "isteyebilirsin.",
                [],
            )

        # Ne oneri ne spesifik kitap sorgusu gibi gorunuyor, ustelik en iyi
        # eslesme de zayifsa: sorgu muhtemelen kitapla ilgisiz (hava durumu,
        # genel sohbet vb.). Alakasiz bir kitap uydurup anlatmak yerine
        # "bilmiyorum" de.
        if not looks_like_recommendation and not looks_like_specific_book and top_score < OFF_TOPIC_THRESHOLD:
            return (
                "Bunu bilmiyorum. Sadece kitap önerileri yapabilir ve "
                "kütüphanemdeki kitaplar hakkında bilgi verebilirim.",
                [],
            )

        # Sorgu acikca bir kitabin adini iceriyorsa (kesin baslik eslesmesi)
        # ve bu bir "oneri" sorgusu degilse: LLM'e SADECE o kitabin ozetini
        # veriyoruz ve gorevini "yeniden ifade et" ile sinirliyoruz. Boylece
        # hem uretim hala LLM'den geciyor hem de halusinasyon riski, aday
        # arasindan sentez yapmaya calismaktan cok daha dusuk oluyor.
        if not looks_like_recommendation:
            top_book, top_score = results[0]
            summary = (top_book.get("summary") or "").strip()
            if top_score >= EXACT_MATCH_THRESHOLD and summary:
                user_prompt = (
                    f"Kitap: {top_book['title_tr']} ({top_book['title_en']})\n"
                    f"Ozet: {summary}\n\n/no_think"
                )
                completion = self._chat_client.chat.completions.create(
                    model=self._chat_model_id,
                    messages=[
                        {"role": "system", "content": SPECIFIC_BOOK_SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.4,
                    max_tokens=1200,
                )
                raw = completion.choices[0].message.content or ""
                cleaned = _truncate_repetition(_cut_at_leak_markers(_strip_think_tags(raw)))
                if len(cleaned) < 15:
                    cleaned = (
                        f"{top_book['title_tr']} hakkinda konusma sirasinda bir "
                        "sorun olustu (model dongu problemi). Lutfen sorguyu "
                        "tekrar dene."
                    )
                return cleaned, results

        context = self._format_context(results) if results else "Kitap listesi bos."
        user_prompt = (
            f"KITAP LISTESI:\n{context}\n\nISTEK: {query}\n\nCEVAP:\n\n/no_think"
        )

        completion = self._chat_client.chat.completions.create(
            model=self._chat_model_id,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.4,
            max_tokens=1400,
        )
        raw = completion.choices[0].message.content or ""
        cleaned = _truncate_repetition(_cut_at_leak_markers(_strip_think_tags(raw)))
        if len(cleaned) < 15:
            cleaned = (
                "Bir oneri olusturulurken model dongu problemi yasadi. "
                "Lutfen sorguyu biraz farkli sekilde tekrar dene."
            )
        return cleaned, results


if __name__ == "__main__":
    engine = RagEngine()
    print(f"Yuklenen kitap sayisi: {len(engine.books)}")
    test_query = input("Sorgu: ")
    reply, hits = engine.answer(test_query)
    print("\n--- YANIT ---")
    print(reply)
    print("\n--- KULLANILAN KITAPLAR ---")
    for book, score in hits:
        print(f"{book['title_tr']} (skor={score:.3f})")
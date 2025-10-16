import React, { useState } from "react";
import { GoogleGenerativeAI } from "@google/generative-ai";
import ReactMarkdown from "react-markdown";
import "./App.css";

function App() {
  const [sentence, setSentence] = useState("");
  const [geminiResponse, setGeminiResponse] = useState(""); // store Gemini output
  const [verificationResult, setVerificationResult] = useState(""); // store verification
  const [loading, setLoading] = useState(false);

  const API_KEY = "AIzaSyC0V_2pfkh5fwOfgvypSKQQ3MyKCbSgM1w";
  const genAI = new GoogleGenerativeAI(API_KEY);
  const model = genAI.getGenerativeModel({ model: "gemini-2.5-flash" });

  // 1️⃣ Search → Gemini
  const handleSearch = async () => {
    if (!sentence.trim()) return alert("Please enter a sentence first!");
    setLoading(true);
    try {
      const result = await model.generateContent(sentence);
      const text = result.response.text(); // get Gemini text output
      setGeminiResponse(await text); // store Gemini response
      setVerificationResult(""); // clear previous verification
    } catch (err) {
      console.error(err);
      setGeminiResponse("Error generating Gemini response.");
    } finally {
      setLoading(false);
    }
  };

  // 2️⃣ Verify → send Gemini response to backend
  const handleVerify = async () => {
    if (!geminiResponse) {
      return alert("Please click 'Search' first to get Gemini response!");
    }

    setLoading(true);
    try {
      const res = await fetch("http://localhost:5000/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sentence: geminiResponse }), // send Gemini output
      });
      const data = await res.json();
      if (data.error) {
        setVerificationResult("Error: " + data.error);
      } else {
        const formatted = `
### Verification Summary
${data.summary}

---

### Raw JSON
\`\`\`json
${JSON.stringify(data.results, null, 2)}
\`\`\`
        `;
        setVerificationResult(formatted);
      }
    } catch (err) {
      console.error(err);
      setVerificationResult("Error connecting to backend.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="container">
      <div className="header">
        <div className="title">🎬 Movie Claim Verifier</div>
        <div className="small">
          First click Search to get Gemini response, then Verify to check claims.
        </div>
      </div>

      <div className="input-area">
        <textarea
          className="sentence"
          value={sentence}
          onChange={(e) => setSentence(e.target.value)}
          placeholder="Enter a movie-related sentence..."
        />

        <div className="controls">
          <button onClick={handleSearch} disabled={loading}>
            {loading ? "Searching…" : "Search"}
          </button>
          <button onClick={handleVerify} disabled={loading}>
            {loading ? "Verifying…" : "Verify"}
          </button>
        </div>
      </div>

      {geminiResponse && (
        <div className="response-box">
          <h3>Gemini Response:</h3>
          <ReactMarkdown>{geminiResponse}</ReactMarkdown>
        </div>
      )}

      {verificationResult && (
        <div className="response-box">
          <h3>Verification Result:</h3>
          <ReactMarkdown>{verificationResult}</ReactMarkdown>
        </div>
      )}
    </div>
  );
}

export default App;

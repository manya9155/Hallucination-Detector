// src/App.js
import React, { useState } from "react";
import { generateContent } from './components/Model';
import ReactMarkdown from 'react-markdown'; 
import "./App.css";

function App() {
  const [sentence, setSentence] = useState("");
  const [response, setResponse] = useState('');
  const [loading, setLoading] = useState(false);

  const geminiApiKey = "AIzaSyCNs-FR4ti3Xz_olgxXQWQt1h8boDWEJhU"; 
  
  const handleSearch = async () => {
      setLoading(true);
      try {
        const geminiResponse = await generateContent(prompt);
        setResponse(geminiResponse);
      } catch (error) {
        console.error("Error generating content:", error);
        setResponse("Error generating response.");
      } finally {
        setLoading(false);
      }
    
};

   function generateContent(prompt) {
    const result = await model.generateContent(prompt);
    const response = await result.response;
    return response.text();
  }


  const handleVerify = () => {
    console.log("Verify clicked. Input:", sentence);
    
  };

  return (
    <div className="container">
      <div className="header">
        <div>
          <div className="title">🎬 Movie Claim Verifier</div>
          <div className="small">
            Type a movie-related sentence and click Search or Search & Verify.
          </div>
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
          <button
            className="searchAndVerify"
            onClick={handleVerify}
            disabled={loading}
          >
            Search and Verify
          </button>
          <button className="search" onClick={handleSearch} disabled={loading}>
            {loading ? "Searching…" : "Search"}
          </button>
        </div>
      </div>

      {response && (
        <div className="response-box">
          <h3>Gemini Response:</h3>
          <p>{response}</p>
        </div>
      )}
    </div>
  );
}

export default App;

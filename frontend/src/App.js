// src/App.js
import React, { useState } from "react";
import { GoogleGenerativeAI } from "@google/generative-ai";
import ReactMarkdown from 'react-markdown';
import "./App.css";

function App() {
  const [sentence, setSentence] = useState("");
  const [response, setResponse] = useState('');
  const [loading, setLoading] = useState(false);

  const API_KEY = "AIzaSyC0V_2pfkh5fwOfgvypSKQQ3MyKCbSgM1w";
  const genAI = new GoogleGenerativeAI(API_KEY);
  const model = genAI.getGenerativeModel({ model: "gemini-2.5-flash" });
  

  const handleSearch = async (e) => {
    e.preventDefault(); // 🔴 prevent reload
    setLoading(true);
    try {
      const geminiResponse = await generateContent(sentence);
      setResponse(geminiResponse);
    } catch (error) {
      console.error("Error generating content:", error);
      setResponse("Error generating response.");
    } finally {
      setLoading(false);
    }
  };
  

  async function generateContent(prompt) {
    const result = await model.generateContent(prompt);
    const response = await result.response;
    return response.text();
  }


  const handleVerify = () => {
    console.log("Verify clicked. Input:", sentence);
    
  };

  // return (
  //   <div className="container">
  //     <div className="header">
  //       <div>
  //         <div className="title">🎬 Movie Claim Verifier</div>
  //         <div className="small">
  //           Type a movie-related sentence and click Search or Search & Verify.
  //         </div>
  //       </div>
  //     </div>

  //     <div className="input-area">
  //       <textarea
  //         className="sentence"
  //         value={sentence}
  //         onChange={(e) => setSentence(e.target.value)}
  //         placeholder="Enter a movie-related sentence..."
  //       />
  //       <div className="controls">
  //         <button
  //           className="searchAndVerify"
  //           onClick={handleVerify}
  //           disabled={loading}
  //         >
  //           Search and Verify
  //         </button>
  //         <button className="search" onClick={handleSearch} disabled={loading}>
  //           {loading ? "Searching…" : "Search"}
  //         </button>
  //       </div>
  //     </div>

  //     {response && (
  //       <div className="response-box">
  //         <h3>Gemini Response:</h3>
  //         <p>{response}</p>
  //       </div>
  //     )}
  //   </div>
  // );
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
    <div>
      <div className="input-area" onSubmit={handleSearch}>
      <textarea
           className="sentence"
           value={sentence}
           onChange={(e) => setSentence(e.target.value)}
           placeholder="Enter a movie-related sentence..."
         />
        {/* <button type="submit" disabled={loading}>
          {loading ? 'Generating...' : 'Send'}
        </button> */}
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
          <ReactMarkdown>{response}</ReactMarkdown> {/* Render markdown */}
        </div>
      )}
    </div>
    </div>
  );
}

export default App;

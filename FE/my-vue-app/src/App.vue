<script setup>
import { ref, nextTick, onMounted } from 'vue'
import axios from 'axios'

const file = ref(null)
const question = ref('')
const loading = ref(false)
const sessionId = ref('')
const documentList = ref([])
const chatHistory = ref([])

// Message type for chat
const createMessage = (role, content, documentContext = null) => ({
  id: Date.now(),
  role,
  content,
  timestamp: new Date().toLocaleTimeString(),
  documentContext
})

// Speech recognition
const recognition = ref(null)
const isSpeechRecognitionSupported = ref(false)
const isListening = ref(false)

// Initialize speech recognition
const initSpeechRecognition = () => {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
  if (SpeechRecognition) {
    try {
      recognition.value = new SpeechRecognition()
      recognition.value.lang = "en-US"
      recognition.value.continuous = false
      recognition.value.interimResults = false
      isSpeechRecognitionSupported.value = true
      
      // Set up event handlers
      recognition.value.onresult = (event) => {
        if (event.results && event.results[0] && event.results[0][0]) {
          const transcript = event.results[0][0].transcript
          question.value = transcript
          // Auto-submit the question after a short delay
          setTimeout(() => {
            if (question.value.trim()) {
              askQuestion()
            }
          }, 500)
        }
        isListening.value = false
      }
      
      recognition.value.onerror = (event) => {
        console.error('Speech recognition error:', event.error)
        addMessage('system', 'Error occurred during speech recognition.')
        isListening.value = false
      }
      
      recognition.value.onend = () => {
        isListening.value = false
      }
      
    } catch (error) {
      console.error('Error initializing speech recognition:', error)
      isSpeechRecognitionSupported.value = false
    }
  }
}

// Initialize on component mount
onMounted(() => {
  initSpeechRecognition()
})

// Toggle voice input
const toggleVoiceInput = () => {
  if (!isSpeechRecognitionSupported.value || !recognition.value) {
    addMessage('system', 'Speech recognition is not supported in your browser.')
    return
  }

  if (isListening.value) {
    stopListening()
  } else {
    startListening()
  }
}

// Start voice recording
const startListening = () => {
  if (isListening.value) return
  
  try {
    question.value = ''
    recognition.value.start()
    isListening.value = true
  } catch (error) {
    console.error('Error starting speech recognition:', error)
    addMessage('system', 'Could not start voice input. Please check your microphone permissions.')
    isListening.value = false
  }
}

// Stop voice recording
const stopListening = () => {
  if (recognition.value && isListening.value) {
    recognition.value.stop()
    isListening.value = false
  }
}

//  Speak the answer
const speakAnswer = (text) => {
  const utterance = new SpeechSynthesisUtterance(text)
  utterance.lang = "en-US"
  window.speechSynthesis.speak(utterance)
}

const handleFileChange = (e) => {
  file.value = e.target.files[0]
}

const addMessage = (role, content, documentContext = null) => {
  chatHistory.value.push(createMessage(role, content, documentContext))
  // Auto-scroll to bottom of chat
  nextTick(() => {
    const chatContainer = document.querySelector('.chat-container')
    if (chatContainer) {
      chatContainer.scrollTop = chatContainer.scrollHeight
    }
  })
}

const askQuestion = async () => {
  if (!file.value || !question.value.trim()) {
    alert("Please upload a file and enter/ask a question")
    return
  }

  const userQuestion = question.value.trim()
  addMessage('user', userQuestion)
  question.value = ''
  loading.value = true
  
  try {
    // Upload file for OCR if not already uploaded
    if (!sessionId.value) {
      const formData = new FormData()
      formData.append("file", file.value)
      const uploadResponse = await axios.post("http://localhost:8000/upload", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      })
      
      if (!uploadResponse.data || !uploadResponse.data.text_length) {
        throw new Error('Failed to process the uploaded file')
      }
    }

    // Prepare form data with session ID if available
    const askForm = new FormData()
    askForm.append("query", userQuestion)
    if (sessionId.value) {
      askForm.append("session_id", sessionId.value)
    }

    // Ask question with timeout
    const res = await Promise.race([
      axios.post("http://localhost:8000/ask", askForm),
      new Promise((_, reject) => 
        setTimeout(() => reject(new Error('Request timeout')), 30000) // 30 second timeout
      )
    ])
    
    // Check for error in response
    if (res.data.error) {
      throw new Error(res.data.error_details || 'Error processing your request')
    }
    
    // Update session ID if this is a new session
    if (res.data.session_id) {
      sessionId.value = res.data.session_id
    }
    
    // Add assistant's response to chat
    addMessage(
      'assistant', 
      res.data.answer,
      res.data.context_used ? { preview: res.data.context_used } : null
    )
    
    // Speak the answer if it's not an error message
    if (!res.data.error) {
      speakAnswer(res.data.answer)
    }
  
  } catch (err) {
    console.error("Error:", err)
    let errorMessage = 'Sorry, an error occurred while processing your request.'
    
    // More specific error messages based on error type
    if (err.message.includes('timeout')) {
      errorMessage = 'The request took too long to process. Please try again.'
    } else if (err.message.includes('Network Error')) {
      errorMessage = 'Unable to connect to the server. Please check your internet connection.'
    } else if (err.message.includes('500')) {
      errorMessage = 'Server error. Please try again later.'
    } else if (err.message.includes('400')) {
      errorMessage = 'Please upload a document before asking questions.'
    }
    
    addMessage('system', errorMessage)
  } finally {
    loading.value = false
  }
}

// Handle Enter key press
const handleKeyPress = (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    askQuestion()
  }
}

const getListDocument = async () => {
  try {
    const res = await axios.get("http://localhost:8000/getListDocument")
    console.log("--> Reply",res)
    if (res.data.documents) {
      documentList.value = res.data.documents
    } else {
      documentList.value = [" No documents found."]
    }
  } catch (error) {
    console.error(error)
    documentList.value = [" Error fetching documents."]
  }
}

const getBlobTable = async () => {
  try {
    const res = await axios.get("http://localhost:8000/getBlobTable")
    console.log("Blob Table Response:", res)
    documentList.value = res.data.documents || [" No content."]
  } catch (error) {
    console.error("Error fetching blob table:", error)
    documentList.value = [" Error fetching table from BLOB."]
  }
}

</script>
<style>
   ul {
    list-style: none;
    padding-left: 0;
    margin-left: 0;
  }
</style>
<template>
  <div class="app">
    <div class="chat-container">
      <div class="chat-header">
        <h2>OCR + Voice Q&A</h2>
        <div class="file-upload">
          <label for="file-upload" class="file-upload-label">
            {{ file ? file.name : 'Upload Document' }}
          </label>
          <input 
            id="file-upload" 
            type="file" 
            @change="handleFileChange" 
            class="file-input"
          />
        </div>
      </div>

      <div class="chat-messages">
        <div 
          v-for="message in chatHistory" 
          :key="message.id"
          :class="['message', message.role]"
        >
          <div class="message-header">
            <span class="role">{{ message.role === 'user' ? 'You' : 'Assistant' }}</span>
            <span class="time">{{ message.timestamp }}</span>
          </div>
          <div class="message-content" style="white-space: pre-line;">
            {{ message.content }}
          </div>
          <div v-if="message.documentContext" class="document-context">
            <small>Context: {{ message.documentContext.preview || 'No context' }}</small>
          </div>
        </div>
        <div v-if="loading" class="message assistant">
          <div class="message-content typing">Thinking...</div>
        </div>
      </div>

      <div class="chat-input">
        <div class="input-group">
          <textarea
            v-model="question"
            @keydown.enter.exact.prevent="askQuestion"/>
          <div class="button-group">
            <!-- Voice input button -->
            <button 
              @click="toggleVoiceInput" 
              class="voice-button"
              :class="{ 'listening': isListening }"
              type="button"
            >
              <i :class="isListening ? 'fas fa-microphone-slash' : 'fas fa-microphone'"></i>
            </button>
            <button @click="askQuestion" :disabled="!question.trim() || loading" class="send-button">
              {{ loading ? 'Sending...' : 'Send' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <div class="documents-panel">
      <div class="documents-header">
  
      <div>
        <button @click="getBlobTable" class="refresh-button">
          Load from DB
        </button>
      </div>
      </div>
      <ul class="document-list">
        <li v-for="(doc, index) in documentList" :key="index" class="document-item">
          <span class="filename">{{ doc.filename }}</span>
          <span class="filepath">{{ doc.filepath }}</span>
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
#app {
    max-width: 100%;
    margin: 0;
    padding: 2rem;
    text-align: center;
    width: 100%;
}
.app {
  display: flex;
  height: 100vh;
  font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
  width: 100%;
  max-width: 100%;
}

.chat-container {
  flex: 3;
  display: flex;
  flex-direction: column;
  border-right: 1px solid #e0e0e0;
  height: 100%;
}

.chat-header {
  padding: 1rem;
  background-color: #f5f5f5;
  border-bottom: 1px solid #e0e0e0;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 1rem;
  background-color: #fafafa;
}

.message {
  margin-bottom: 1rem;
  max-width: 80%;
  padding: 0.75rem 1rem;
  border-radius: 1rem;
  position: relative;
  animation: fadeIn 0.3s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.message.user {
  background-color: #e3f2fd;
  margin-left: auto;
  border-bottom-right-radius: 0.25rem;
}

.message.assistant {
  background-color: #f1f1f1;
  margin-right: auto;
  border-bottom-left-radius: 0.25rem;
}

.message.system {
  background-color: #fff8e1;
  margin: 1rem auto;
  text-align: center;
  max-width: 90%;
  font-style: italic;
  font-size: 0.9em;
  color: #666;
}

.message-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 0.5rem;
  font-size: 0.8em;
  color: #666;
}

.message-content {
  line-height: 1.5;
  word-wrap: break-word;
}

.document-context {
  margin-top: 0.5rem;
  padding-top: 0.5rem;
  border-top: 1px dashed #ddd;
  font-size: 0.8em;
  color: #666;
}

.chat-input {
  padding: 1rem;
  background-color: #fff;
  border-top: 1px solid #e0e0e0;
}

.input-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

textarea {
  width: 100%;
  padding: 0.75rem;
  border: 1px solid #ddd;
  border-radius: 0.5rem;
  resize: none;
  font-family: inherit;
  font-size: 1em;
  transition: border-color 0.2s;
}

textarea:focus {
  outline: none;
  border-color: #2196f3;
  box-shadow: 0 0 0 2px rgba(33, 150, 243, 0.2);
}

.button-group {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

button {
  padding: 0.5rem 1rem;
  border: none;
  border-radius: 0.5rem;
  background-color: #2196f3;
  color: white;
  cursor: pointer;
  font-weight: 500;
  transition: background-color 0.2s;
}

button:hover:not(:disabled) {
  background-color: #1976d2;
}

button:disabled {
  background-color: #bdbdbd;
  cursor: not-allowed;
}

/* Voice button styles */
.voice-button {
  background: #4CAF50;
  color: white;
  border: none;
  border-radius: 50%;
  width: 40px;
  height: 40px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-left: 8px;
  transition: all 0.3s ease;
}

.voice-button:hover {
  background: #45a049;
  transform: scale(1.05);
}

.voice-button:active {
  transform: scale(0.95);
}

.voice-button.listening {
  background: #f44336;
  animation: pulse 1.5s infinite;
}

@keyframes pulse {
  0% {
    box-shadow: 0 0 0 0 rgba(244, 67, 54, 0.7);
  }
  70% {
    box-shadow: 0 0 0 10px rgba(244, 67, 54, 0);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(244, 67, 54, 0);
  }
}

.icon-button {
  background: none;
  color: #2196f3;
  font-size: 1.2em;
  padding: 0.5rem;
}

.send-button {
  padding: 0.5rem 1.5rem;
}

.documents-panel {
  flex: 1;
  padding: 1rem;
  background-color: #f9f9f9;
  overflow-y: auto;
}

.documents-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid #e0e0e0;
}

.document-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.document-item {
  padding: 0.75rem;
  margin-bottom: 0.5rem;
  background-color: white;
  border-radius: 0.5rem;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  transition: transform 0.2s;
}

.document-item:hover {
  transform: translateX(4px);
}

.filename {
  display: block;
  font-weight: 500;
  margin-bottom: 0.25rem;
}

.filepath {
  display: block;
  font-size: 0.8em;
  color: #666;
  word-break: break-all;
}

.typing {
  position: relative;
  color: #666;
}

.typing::after {
  content: '...';
  position: absolute;
  animation: typing 1.5s infinite;
}

@keyframes typing {
  0% { content: '.'; }
  33% { content: '..'; }
  66% { content: '...'; }
}

.file-upload {
  position: relative;
  overflow: hidden;
  display: inline-block;
}

.file-upload-label {
  display: inline-block;
  padding: 0.5rem 1rem;
  background-color: #e3f2fd;
  color: #1976d2;
  border-radius: 0.5rem;
  cursor: pointer;
  transition: background-color 0.2s;
}

.file-upload-label:hover {
  background-color: #bbdefb;
}

.file-input {
  position: absolute;
  left: 0;
  top: 0;
  opacity: 0;
  width: 100%;
  height: 100%;
  cursor: pointer;
}
</style>

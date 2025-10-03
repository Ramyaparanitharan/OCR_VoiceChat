# OCR Voice Chat

This is the frontend application for the OCR Voice Chat system, built with Vue.js 3, TypeScript, and Vite. The application provides a user-friendly interface for interacting with the OCR and voice processing backend.

## Features

- Voice-to-text input using Web Speech API
- Document upload and management
- Real-time chat interface
- Responsive design for desktop and mobile
- Speech synthesis for responses
- File upload progress tracking
- Session management

## Prerequisites

- Node.js (v16 or higher)
- npm (v8 or higher) or yarn
- Backend API server (must be running)

## Project Setup

1. Navigate to the frontend directory:
   ```bash
   cd D:\OKR\OCR_VoiceChat\FE\my-vue-app
   ```

2. Install dependencies:
   ```bash
   npm install
   # or
   yarn install
   ```

## Configuration

Before running the application, you may need to configure the backend API URL. The application makes API calls to the backend server. By default, it uses:

```env
VITE_API_URL=http://localhost:8000
```

You can create a `.env` file in the `my-vue-app` directory to override this setting.

## Available Scripts

### Development Server

Start the development server with hot-reload:
```bash
npm run dev
# or
yarn dev
```

The application will be available at `http://localhost:5173`

### Build for Production

Build the application for production:
```bash
npm run build
# or
yarn build
```

The built files will be in the `dist/` directory.

### Preview Production Build

Preview the production build locally:
```bash
npm run preview
# or
yarn preview
```

## Project Structure

```
my-vue-app/
├── public/              # Static files
├── src/
│   ├── App.vue         # Main application component
│   ├── main.ts         # Application entry point
│   ├── style.css       # Global styles
│   └── typescript.svg  # Assets
├── .gitignore
├── index.html          # Main HTML file
├── package.json        # Project configuration
├── tsconfig.json       # TypeScript configuration
└── vite.config.ts      # Vite configuration
```

## Key Components

### App.vue

The main application component that handles:
- Voice input/output
- Chat interface
- File uploads
- API communication
- State management

## API Integration

The frontend communicates with the backend using Axios. The main API endpoints used are:

- `POST /upload`: Upload documents
- `POST /chat`: Send chat messages
- `GET /documents`: List uploaded documents
- `GET /session`: Manage chat sessions

## Browser Support

The application uses modern web APIs including:
- Web Speech API (for voice input/output)
- Fetch API
- ES6+ features

For best compatibility, use the latest versions of:
- Google Chrome


Quick Start (middleware)

1. Navigate to the middleware directory
2. Install dependencies : pip install -r ..\requirements.txt
3. Create a .env file with your AWS credentials and other settings.
4. Start the server: python fastAPI.py


Note : Refer https://core.elsaifoundry.ai/user-guide/elsai-utilities.html for elsai utility package details

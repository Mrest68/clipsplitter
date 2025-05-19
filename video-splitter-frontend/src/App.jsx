import { useState, useCallback, useEffect } from 'react';
import { useDropzone } from 'react-dropzone';
import axios from 'axios';
import './App.css';

// API base URL - adjust based on where your Flask backend is running
const API_BASE_URL = 'http://127.0.0.1:5000';

function App() {
  const [file, setFile] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [processingStatus, setProcessingStatus] = useState('');
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [errorDetails, setErrorDetails] = useState('');
  const [savePath, setSavePath] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [saveResult, setSaveResult] = useState(null);
  const [apiStatus, setApiStatus] = useState(null);

  // Check if the API is running
  useEffect(() => {
    const checkApiStatus = async () => {
      try {
        const response = await axios.get(`${API_BASE_URL}/`, { timeout: 5000 });
        setApiStatus({ running: true, message: 'API is running' });
      } catch (err) {
        console.error('API check error:', err);
        setApiStatus({ 
          running: false, 
          message: 'API is not running. Please make sure the backend server is started.' 
        });
      }
    };

    checkApiStatus();
    
    // Check API status every 10 seconds
const intervalId = setInterval(checkApiStatus, 90000);

    
    // Clean up interval on component unmount
    return () => clearInterval(intervalId);
  }, []);

  const onDrop = useCallback(acceptedFiles => {
    if (acceptedFiles.length > 0) {
      const selectedFile = acceptedFiles[0];
      console.log('File selected:', selectedFile.name, selectedFile.type, selectedFile.size);
      setFile(selectedFile);
      setError('');
      setErrorDetails('');
      setResult(null);
      setSaveResult(null);
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'video/*': ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm', '.m4v', '.3gp']
    },
    maxFiles: 1
  });

  const handleUpload = async () => {
    if (!file) {
      setError('Please select a video file first');
      return;
    }

    if (!apiStatus?.running) {
      setError('Backend API is not running. Please start the server.');
      return;
    }

    setIsUploading(true);
    setUploadProgress(0);
    setProcessingStatus('Uploading video...');
    setError('');
    setErrorDetails('');
    setResult(null);
    setSaveResult(null);

    console.log('Starting upload of file:', file.name);
    const formData = new FormData();
    formData.append('file', file);

    try {
      console.log('Sending request to API...');
      const response = await axios.post(`${API_BASE_URL}/api/upload`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data'
        },
        onUploadProgress: (progressEvent) => {
          const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          console.log(`Upload progress: ${percentCompleted}%`);
          setUploadProgress(percentCompleted);
        },
        timeout: 300000 // 5 minutes
      });

      console.log('API response:', response.data);
      setProcessingStatus('Processing complete!');
      setResult(response.data);
    } catch (err) {
      console.error('Upload error:', err);
      let errorMsg = 'Error uploading and processing video';
      let errorDetailsMsg = '';
      
      if (err.response) {
        console.error('Error response data:', err.response.data);
        console.error('Error response status:', err.response.status);
        
        errorMsg = err.response.data.error || errorMsg;
        errorDetailsMsg = `Status: ${err.response.status}`;
      } else if (err.request) {
        console.error('Error request:', err.request);
        errorMsg = 'No response from server. Is the backend running?';
        errorDetailsMsg = 'Check that the Flask server is running on port 5000.';
      } else {
        console.error('Error message:', err.message);
        errorMsg = err.message || errorMsg;
      }
      
      setError(errorMsg);
      setErrorDetails(errorDetailsMsg);
    } finally {
      setIsUploading(false);
    }
  };

  const handleDownload = (videoId, filename) => {
    console.log(`Downloading file: ${videoId}/${filename}`);
    window.open(`${API_BASE_URL}/api/download/${videoId}/${filename}`, '_blank');
  };

  const handleSaveToPath = async () => {
    if (!result || !savePath) {
      setError('Missing result or save path');
      return;
    }

    setIsSaving(true);
    setSaveResult(null);
    setError('');
    setErrorDetails('');

    console.log(`Saving files to path: ${savePath}`);
    try {
      const response = await axios.post(`${API_BASE_URL}/api/save-to-path`, {
        video_id: result.video_id,
        path: savePath
      });

      console.log('Save response:', response.data);
      setSaveResult(response.data);
    } catch (err) {
      console.error('Save error:', err);
      let errorMsg = 'Error saving files to the specified path';
      let errorDetailsMsg = '';
      
      if (err.response) {
        console.error('Error response data:', err.response.data);
        errorMsg = err.response.data.error || errorMsg;
        errorDetailsMsg = `Status: ${err.response.status}`;
      } else if (err.request) {
        errorMsg = 'No response from server';
        errorDetailsMsg = 'Check that the Flask server is running.';
      } else {
        errorMsg = err.message || errorMsg;
      }
      
      setError(errorMsg);
      setErrorDetails(errorDetailsMsg);
    } finally {
      setIsSaving(false);
    }
  };

  const formatDuration = (seconds) => {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
  };

  return (
    <div className="app-container">
      <h1>Video Clip Splitter</h1>
      <p className="app-description">
        Drag and drop your video file to split it into smaller clips of optimal length.
      </p>

      {apiStatus && !apiStatus.running && (
        <div className="api-status-error">
          <p><strong>Backend Connection Error:</strong> {apiStatus.message}</p>
          <p>Please make sure the Flask backend is running on port 5000.</p>
        </div>
      )}

      <div className="main-content">
        <div className="upload-section">
          <div 
            {...getRootProps()} 
            className={`dropzone ${isDragActive ? 'active' : ''} ${file ? 'has-file' : ''}`}
          >
            <input {...getInputProps()} />
            {file ? (
              <div className="file-info">
                <p className="file-name">{file.name}</p>
                <p className="file-size">{(file.size / (1024 * 1024)).toFixed(2)} MB</p>
                <p className="file-type">Type: {file.type || 'Unknown'}</p>
              </div>
            ) : (
              <p>{isDragActive ? 'Drop the video here' : 'Drag & drop a video file here, or click to select'}</p>
            )}
          </div>

          {file && !isUploading && !result && (
            <button 
              className="upload-button" 
              onClick={handleUpload}
              disabled={isUploading || !apiStatus?.running}
            >
              Process Video
            </button>
          )}

          {isUploading && (
            <div className="progress-container">
              <div className="progress-bar">
                <div 
                  className="progress-fill" 
                  style={{ width: `${uploadProgress}%` }}
                ></div>
              </div>
              <p className="progress-text">{processingStatus}</p>
              <p className="progress-percentage">{uploadProgress}%</p>
            </div>
          )}

          {error && (
            <div className="error-container">
              <p className="error-message">{error}</p>
              {errorDetails && <p className="error-details">{errorDetails}</p>}
            </div>
          )}
        </div>

        {result && result.result && (
          <div className="results-section">
            <h2>Processing Results</h2>
            
            <div className="video-info">
              <p><strong>Original Duration:</strong> {formatDuration(result.result.duration)}</p>
              <p><strong>Segments Created:</strong> {result.result.segments.length}</p>
              {result.result.segment_length && (
                <p><strong>Segment Length:</strong> ~{formatDuration(result.result.segment_length)}</p>
              )}
            </div>

            <h3>Clips</h3>
            <div className="clips-container">
              {result.result.segments.map((segment, index) => (
                <div className="clip-item" key={index}>
                  <div className="clip-info">
                    <p className="clip-name">{segment.path}</p>
                    <p className="clip-duration">{formatDuration(segment.duration)}</p>
                    {segment.start_time !== undefined && (
                      <p className="clip-start">Start: {formatDuration(segment.start_time)}</p>
                    )}
                  </div>
                  <button 
                    className="download-button"
                    onClick={() => handleDownload(result.video_id, segment.path)}
                  >
                    Download
                  </button>
                </div>
              ))}
            </div>

            <div className="save-locally-section">
              <h3>Save All Clips to Local Path</h3>
              <div className="save-input-container">
                <input
                  type="text"
                  placeholder="Enter local path (e.g., /Users/username/Desktop)"
                  value={savePath}
                  onChange={(e) => setSavePath(e.target.value)}
                  className="path-input"
                />
                <button 
                  className="save-button"
                  onClick={handleSaveToPath}
                  disabled={isSaving || !savePath}
                >
                  {isSaving ? 'Saving...' : 'Save All Clips'}
                </button>
              </div>

              {saveResult && (
                <div className="save-result">
                  <p className="success-message">{saveResult.message}</p>
                  <p>Files saved: {saveResult.files.join(', ')}</p>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
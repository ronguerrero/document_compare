import { useState, useCallback, useEffect } from 'react';
import { FileText, ArrowRightLeft, Loader2, CheckCircle, AlertTriangle, XCircle, FileUp, Brain, ChevronDown } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

interface SectionPreview { title: string; preview: string; }
interface ModelInfo { id: string; name: string; provider: string; }
interface ComparisonResult {
  pptx_file: string; doc_file: string; model: string;
  pptx_sections: number; doc_sections: number;
  pptx_content: SectionPreview[]; doc_content: SectionPreview[];
  pptx_markdown: string; doc_markdown: string;
  comparison_report: string;
}

const PROVIDER_COLORS: Record<string, string> = {
  Meta: '#1877F2', Anthropic: '#D4A574', OpenAI: '#10A37F', Google: '#4285F4',
};

function DropZone({ label, accept, file, onFile, icon: Icon }: {
  label: string; accept: string; file: File | null; onFile: (f: File) => void; icon: React.ElementType;
}) {
  const [dragOver, setDragOver] = useState(false);
  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault(); setDragOver(false);
    if (e.dataTransfer.files[0]) onFile(e.dataTransfer.files[0]);
  }, [onFile]);

  return (
    <div onDragOver={(e) => { e.preventDefault(); setDragOver(true); }} onDragLeave={() => setDragOver(false)} onDrop={handleDrop}
      className={`relative flex flex-col items-center justify-center p-8 border-2 border-dashed rounded-xl transition-all cursor-pointer
        ${dragOver ? 'border-blue-400 bg-blue-500/10' : file ? 'border-green-500/50 bg-green-500/5' : 'border-gray-700 bg-gray-900 hover:border-gray-500'}`}>
      <input type="file" accept={accept} className="absolute inset-0 opacity-0 cursor-pointer"
        onChange={(e) => { if (e.target.files?.[0]) onFile(e.target.files[0]); }} />
      {file ? (
        <><CheckCircle size={32} className="text-green-400 mb-2" />
          <p className="text-sm font-medium text-green-300">{file.name}</p>
          <p className="text-xs text-gray-500 mt-1">{(file.size / 1024).toFixed(0)} KB</p></>
      ) : (
        <><Icon size={32} className="text-gray-500 mb-2" />
          <p className="text-sm font-medium text-gray-400">{label}</p>
          <p className="text-xs text-gray-600 mt-1">Drag & drop or click to browse</p></>
      )}
    </div>
  );
}

function SectionList({ title, sections, color }: { title: string; sections: SectionPreview[]; color: string }) {
  return (
    <div>
      <h3 className={`text-sm font-semibold mb-2 ${color}`}>{title} ({sections.length} sections)</h3>
      <div className="space-y-2 max-h-64 overflow-y-auto">
        {sections.map((s, i) => (
          <div key={i} className="bg-gray-800/50 rounded-lg p-3 border border-gray-700/50">
            <p className="text-xs font-semibold text-gray-300">{s.title}</p>
            <p className="text-xs text-gray-500 mt-1 line-clamp-2">{s.preview}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function MarkdownPreview({ title, content }: { title: string; content: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl">
      <button onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between p-4 text-left hover:bg-gray-800/50 transition-colors rounded-xl">
        <span className="text-sm font-medium text-gray-400">{title}</span>
        <ChevronDown size={16} className={`text-gray-500 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="px-4 pb-4">
          <pre className="text-xs text-gray-500 bg-gray-950 rounded-lg p-4 overflow-x-auto max-h-80 overflow-y-auto whitespace-pre-wrap">{content}</pre>
        </div>
      )}
    </div>
  );
}

export default function App() {
  const [pptxFile, setPptxFile] = useState<File | null>(null);
  const [docFile, setDocFile] = useState<File | null>(null);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [selectedModel, setSelectedModel] = useState('databricks-gemini-2-5-flash');
  const [showModels, setShowModels] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadingStatus, setLoadingStatus] = useState('');
  const [result, setResult] = useState<ComparisonResult | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    fetch('/api/models').then(r => r.json()).then(d => {
      setModels(d.models || []);
    }).catch(() => {});
  }, []);

  const currentModel = models.find(m => m.id === selectedModel);

  const compare = async () => {
    if (!pptxFile || !docFile) return;
    setLoading(true); setError(''); setResult(null);
    setLoadingStatus('Parsing documents to markdown...');

    const form = new FormData();
    form.append('pptx_file', pptxFile);
    form.append('doc_file', docFile);
    form.append('model', selectedModel);

    try {
      setTimeout(() => setLoadingStatus(`Comparing with ${currentModel?.name || selectedModel}...`), 3000);
      const res = await fetch('/api/compare', { method: 'POST', body: form });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.error || `HTTP ${res.status}`);
      }
      setResult(await res.json());
    } catch (e: any) {
      setError(e.message || 'Comparison failed');
    } finally {
      setLoading(false); setLoadingStatus('');
    }
  };

  const reset = () => {
    setPptxFile(null); setDocFile(null); setResult(null); setError('');
  };

  return (
    <div className="min-h-screen">
      <header className="border-b border-gray-800 bg-gray-900/80 backdrop-blur sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <ArrowRightLeft size={24} className="text-blue-400" />
            <div>
              <h1 className="text-lg font-bold">Document Comparator</h1>
              <p className="text-xs text-gray-500">Parse to markdown, compare with AI</p>
            </div>
          </div>
          {/* Model Selector */}
          <div className="relative">
            <button onClick={() => setShowModels(!showModels)}
              className="flex items-center gap-2 px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg hover:bg-gray-700 transition-colors">
              <Brain size={16} style={{ color: PROVIDER_COLORS[currentModel?.provider || ''] || '#888' }} />
              <span className="text-sm">{currentModel?.name || 'Select Model'}</span>
              <ChevronDown size={14} className="text-gray-500" />
            </button>
            {showModels && (
              <div className="absolute right-0 top-12 w-72 bg-gray-900 border border-gray-700 rounded-xl shadow-2xl z-20 py-2">
                {models.map(m => (
                  <button key={m.id} onClick={() => { setSelectedModel(m.id); setShowModels(false); }}
                    className={`w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-gray-800 transition-colors
                      ${m.id === selectedModel ? 'bg-gray-800/60' : ''}`}>
                    <div className="w-2 h-2 rounded-full" style={{ background: PROVIDER_COLORS[m.provider] || '#888' }} />
                    <div>
                      <div className="text-sm font-medium">{m.name}</div>
                      <div className="text-[10px] text-gray-500">{m.provider}</div>
                    </div>
                    {m.id === selectedModel && <CheckCircle size={14} className="ml-auto text-blue-400" />}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-8">
        {!result && (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
              <div>
                <label className="block text-sm font-medium text-gray-400 mb-2">PowerPoint Presentation (.pptx)</label>
                <DropZone label="Upload PowerPoint" accept=".pptx" file={pptxFile} onFile={setPptxFile} icon={FileUp} />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-400 mb-2">Document (.docx or .txt)</label>
                <DropZone label="Upload Document" accept=".docx,.txt" file={docFile} onFile={setDocFile} icon={FileText} />
              </div>
            </div>

            <div className="flex flex-col items-center gap-3">
              <button onClick={compare} disabled={!pptxFile || !docFile || loading}
                className="flex items-center gap-2 px-8 py-3 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 text-white font-medium rounded-lg transition-colors">
                {loading ? (
                  <><Loader2 size={18} className="animate-spin" /> {loadingStatus}</>
                ) : (
                  <><ArrowRightLeft size={18} /> Compare with {currentModel?.name || 'AI'}</>
                )}
              </button>
              {!loading && (
                <p className="text-xs text-gray-600">
                  Using <span className="text-gray-400">{currentModel?.name}</span> via Databricks Model Serving
                </p>
              )}
            </div>

            {error && (
              <div className="mt-6 p-4 bg-red-500/10 border border-red-500/30 rounded-lg flex items-start gap-3">
                <XCircle size={18} className="text-red-400 mt-0.5 shrink-0" />
                <p className="text-sm text-red-300">{error}</p>
              </div>
            )}
          </>
        )}

        {result && (
          <div className="space-y-6">
            {/* Summary Bar */}
            <div className="flex items-center justify-between bg-gray-900 border border-gray-800 rounded-xl p-4">
              <div className="flex items-center gap-6">
                <div>
                  <p className="text-xs text-gray-500">PowerPoint</p>
                  <p className="text-sm font-medium">{result.pptx_file}</p>
                </div>
                <ArrowRightLeft size={20} className="text-blue-400" />
                <div>
                  <p className="text-xs text-gray-500">Document</p>
                  <p className="text-sm font-medium">{result.doc_file}</p>
                </div>
                <div className="border-l border-gray-700 pl-6">
                  <p className="text-xs text-gray-500">Model</p>
                  <p className="text-sm font-medium" style={{ color: PROVIDER_COLORS[models.find(m => m.id === result.model)?.provider || ''] }}>
                    {models.find(m => m.id === result.model)?.name || result.model}
                  </p>
                </div>
              </div>
              <button onClick={reset} className="px-4 py-2 text-sm bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors">
                New Comparison
              </button>
            </div>

            {/* Parsed Content Preview */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <SectionList title="PowerPoint Content" sections={result.pptx_content} color="text-orange-400" />
              <SectionList title="Document Content" sections={result.doc_content} color="text-blue-400" />
            </div>

            {/* Markdown Previews (collapsible) */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <MarkdownPreview title="PowerPoint Markdown" content={result.pptx_markdown} />
              <MarkdownPreview title="Document Markdown" content={result.doc_markdown} />
            </div>

            {/* AI Comparison Report */}
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
              <div className="flex items-center gap-2 mb-4">
                <AlertTriangle size={18} className="text-yellow-400" />
                <h2 className="text-lg font-bold">AI Alignment Analysis</h2>
                <span className="text-xs text-gray-500 ml-2">
                  by {models.find(m => m.id === result.model)?.name}
                </span>
              </div>
              <div className="prose prose-invert prose-sm max-w-none
                prose-headings:text-gray-200 prose-h2:text-base prose-h2:border-b prose-h2:border-gray-800 prose-h2:pb-2 prose-h2:mt-6
                prose-p:text-gray-400 prose-li:text-gray-400 prose-strong:text-gray-200
                prose-ul:list-disc prose-ol:list-decimal">
                <ReactMarkdown>{result.comparison_report}</ReactMarkdown>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

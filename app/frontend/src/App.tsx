import { useState, useCallback, useEffect } from 'react';
import { FileText, ArrowRightLeft, Loader2, CheckCircle, AlertTriangle, XCircle, FileUp, Brain, ChevronDown, Cpu } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

interface SectionPreview { title: string; preview: string; }
interface ModelInfo { id: string; name: string; provider: string; }
interface EngineInfo { id: string; name: string; description: string; }
interface ComparisonResult {
  pptx_file: string; doc_file: string; model: string; engine: string;
  pptx_sections: number; doc_sections: number;
  pptx_content: SectionPreview[]; doc_content: SectionPreview[];
  pptx_markdown: string; doc_markdown: string;
  comparison_report: string;
}

const PROVIDER_COLORS: Record<string, string> = {
  Meta: '#1877F2', Anthropic: '#D4A574', OpenAI: '#10A37F', Google: '#4285F4',
};
const ENGINE_COLORS: Record<string, string> = {
  ai_functions: '#FF3621', direct_llm: '#00A972',
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

function Dropdown({ label, icon: Icon, iconColor, value, options, renderOption, onSelect, show, setShow }: {
  label: string; icon: React.ElementType; iconColor: string; value: string;
  options: any[]; renderOption: (o: any) => React.ReactNode;
  onSelect: (o: any) => void; show: boolean; setShow: (s: boolean) => void;
}) {
  return (
    <div className="relative">
      <button onClick={() => setShow(!show)}
        className="flex items-center gap-2 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg hover:bg-gray-700 transition-colors text-sm">
        <Icon size={14} style={{ color: iconColor }} />
        <span>{label}</span>
        <ChevronDown size={12} className="text-gray-500" />
      </button>
      {show && (
        <div className="absolute right-0 top-11 w-72 bg-gray-900 border border-gray-700 rounded-xl shadow-2xl z-20 py-2">
          {options.map((o, i) => (
            <button key={i} onClick={() => { onSelect(o); setShow(false); }}
              className="w-full text-left px-4 py-3 hover:bg-gray-800 transition-colors">
              {renderOption(o)}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default function App() {
  const [pptxFile, setPptxFile] = useState<File | null>(null);
  const [docFile, setDocFile] = useState<File | null>(null);
  const [deltaTable, setDeltaTable] = useState('');
  const [compareMode, setCompareMode] = useState<'file' | 'delta'>('file');
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [engines, setEngines] = useState<EngineInfo[]>([]);
  const [selectedModel, setSelectedModel] = useState('databricks-meta-llama-3-3-70b-instruct');
  const [selectedEngine, setSelectedEngine] = useState('direct_llm');
  const [showModels, setShowModels] = useState(false);
  const [showEngines, setShowEngines] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadingStatus, setLoadingStatus] = useState('');
  const [result, setResult] = useState<ComparisonResult | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    fetch('/api/models').then(r => r.json()).then(d => setModels(d.models || [])).catch(() => {});
    fetch('/api/engines').then(r => r.json()).then(d => setEngines(d.engines || [])).catch(() => {});
  }, []);

  const currentModel = models.find(m => m.id === selectedModel);
  const currentEngine = engines.find(e => e.id === selectedEngine);

  const compare = async () => {
    if (!pptxFile) return;
    if (compareMode === 'file' && !docFile) return;
    if (compareMode === 'delta' && !deltaTable.trim()) return;
    setLoading(true); setError(''); setResult(null);

    const engineLabel = currentEngine?.name || selectedEngine;
    setLoadingStatus(`Parsing documents (${engineLabel})...`);

    const form = new FormData();
    form.append('pptx_file', pptxFile);
    if (compareMode === 'file' && docFile) {
      form.append('doc_file', docFile);
    }
    form.append('model', selectedModel);
    form.append('engine', selectedEngine);
    if (compareMode === 'delta') {
      form.append('delta_table', deltaTable);
    }

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

  const canCompare = pptxFile && (compareMode === 'file' ? docFile : deltaTable.trim());
  const reset = () => { setPptxFile(null); setDocFile(null); setDeltaTable(''); setResult(null); setError(''); };

  return (
    <div className="min-h-screen">
      <header className="border-b border-gray-800 bg-gray-900/80 backdrop-blur sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <ArrowRightLeft size={24} className="text-blue-400" />
            <div>
              <h1 className="text-lg font-bold">Document Comparator</h1>
              <p className="text-xs text-gray-500">AI-powered alignment analysis</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {/* Engine Selector */}
            <Dropdown
              label={currentEngine?.name || 'Engine'}
              icon={Cpu}
              iconColor={ENGINE_COLORS[selectedEngine] || '#888'}
              value={selectedEngine}
              options={engines}
              show={showEngines}
              setShow={(s) => { setShowEngines(s); if (s) setShowModels(false); }}
              onSelect={(e) => setSelectedEngine(e.id)}
              renderOption={(e: EngineInfo) => (
                <div>
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full" style={{ background: ENGINE_COLORS[e.id] || '#888' }} />
                    <span className="text-sm font-medium">{e.name}</span>
                    {e.id === selectedEngine && <CheckCircle size={12} className="ml-auto text-blue-400" />}
                  </div>
                  <p className="text-[10px] text-gray-500 mt-1 ml-4">{e.description}</p>
                </div>
              )}
            />
            {/* Model Selector */}
            <Dropdown
              label={currentModel?.name || 'Model'}
              icon={Brain}
              iconColor={PROVIDER_COLORS[currentModel?.provider || ''] || '#888'}
              value={selectedModel}
              options={models}
              show={showModels}
              setShow={(s) => { setShowModels(s); if (s) setShowEngines(false); }}
              onSelect={(m) => setSelectedModel(m.id)}
              renderOption={(m: ModelInfo) => (
                <div className="flex items-center gap-3">
                  <div className="w-2 h-2 rounded-full" style={{ background: PROVIDER_COLORS[m.provider] || '#888' }} />
                  <div>
                    <div className="text-sm font-medium">{m.name}</div>
                    <div className="text-[10px] text-gray-500">{m.provider}</div>
                  </div>
                  {m.id === selectedModel && <CheckCircle size={12} className="ml-auto text-blue-400" />}
                </div>
              )}
            />
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
                <div className="flex items-center gap-2 mb-2">
                  <label className="text-sm font-medium text-gray-400">Compare Against</label>
                  <div className="flex bg-gray-800 rounded-lg p-0.5 ml-auto">
                    <button onClick={() => setCompareMode('file')}
                      className={`px-3 py-1 text-xs rounded-md transition-colors ${compareMode === 'file' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-gray-200'}`}>
                      File
                    </button>
                    <button onClick={() => setCompareMode('delta')}
                      className={`px-3 py-1 text-xs rounded-md transition-colors ${compareMode === 'delta' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-gray-200'}`}>
                      Delta Table
                    </button>
                  </div>
                </div>
                {compareMode === 'file' ? (
                  <DropZone label="Upload Document (.docx, .xlsx, .pdf, .txt)" accept=".docx,.xlsx,.pdf,.txt" file={docFile} onFile={setDocFile} icon={FileText} />
                ) : (
                  <div className={`flex flex-col items-center justify-center p-8 border-2 border-dashed rounded-xl ${deltaTable.trim() ? 'border-green-500/50 bg-green-500/5' : 'border-gray-700 bg-gray-900'}`}>
                    <Cpu size={28} className="text-gray-500 mb-3" />
                    <input
                      type="text"
                      placeholder="catalog.schema.table_name"
                      value={deltaTable}
                      onChange={(e) => setDeltaTable(e.target.value)}
                      className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-blue-500"
                    />
                    <p className="text-[10px] text-gray-600 mt-2">Enter a Unity Catalog table path</p>
                  </div>
                )}
              </div>
            </div>

            <div className="flex flex-col items-center gap-3">
              <button onClick={compare} disabled={!canCompare || loading}
                className="flex items-center gap-2 px-8 py-3 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 text-white font-medium rounded-lg transition-colors">
                {loading ? (
                  <><Loader2 size={18} className="animate-spin" /> {loadingStatus}</>
                ) : (
                  <><ArrowRightLeft size={18} /> Compare Documents</>
                )}
              </button>
              {!loading && (
                <p className="text-xs text-gray-600">
                  <span style={{ color: ENGINE_COLORS[selectedEngine] }}>{currentEngine?.name}</span>
                  {' + '}
                  <span style={{ color: PROVIDER_COLORS[currentModel?.provider || ''] }}>{currentModel?.name}</span>
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
                <div className="border-l border-gray-700 pl-6 flex gap-4">
                  <div>
                    <p className="text-xs text-gray-500">Engine</p>
                    <p className="text-sm font-medium" style={{ color: ENGINE_COLORS[result.engine] }}>
                      {engines.find(e => e.id === result.engine)?.name || result.engine}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-500">Model</p>
                    <p className="text-sm font-medium" style={{ color: PROVIDER_COLORS[models.find(m => m.id === result.model)?.provider || ''] }}>
                      {models.find(m => m.id === result.model)?.name || result.model}
                    </p>
                  </div>
                </div>
              </div>
              <button onClick={reset} className="px-4 py-2 text-sm bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors">
                New Comparison
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <SectionList title="PowerPoint Content" sections={result.pptx_content} color="text-orange-400" />
              <SectionList title="Document Content" sections={result.doc_content} color="text-blue-400" />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <MarkdownPreview title="PowerPoint Parsed Text" content={result.pptx_markdown} />
              <MarkdownPreview title="Document Parsed Text" content={result.doc_markdown} />
            </div>

            <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
              <div className="flex items-center gap-2 mb-4">
                <AlertTriangle size={18} className="text-yellow-400" />
                <h2 className="text-lg font-bold">AI Alignment Analysis</h2>
                <span className="text-xs text-gray-500 ml-2">
                  by {models.find(m => m.id === result.model)?.name} via {engines.find(e => e.id === result.engine)?.name}
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

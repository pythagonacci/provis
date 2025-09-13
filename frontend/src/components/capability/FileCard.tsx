'use client';

import { File, Code, Database, Globe, Settings } from 'lucide-react';

interface FileCardProps {
  file: string;
}

export default function FileCard({ file }: FileCardProps) {
  const getFileIcon = (filePath: string) => {
    if (filePath.includes('.py') || filePath.includes('.js') || filePath.includes('.ts')) {
      return <Code className="w-4 h-4 text-blue-600" />;
    }
    if (filePath.includes('.sql') || filePath.includes('model') || filePath.includes('schema')) {
      return <Database className="w-4 h-4 text-green-600" />;
    }
    if (filePath.includes('.html') || filePath.includes('.css') || filePath.includes('component')) {
      return <Globe className="w-4 h-4 text-purple-600" />;
    }
    if (filePath.includes('config') || filePath.includes('setting')) {
      return <Settings className="w-4 h-4 text-gray-600" />;
    }
    return <File className="w-4 h-4 text-gray-500" />;
  };

  const getFileType = (filePath: string) => {
    if (filePath.includes('.py')) return 'Python';
    if (filePath.includes('.js')) return 'JavaScript';
    if (filePath.includes('.ts')) return 'TypeScript';
    if (filePath.includes('.tsx')) return 'React TSX';
    if (filePath.includes('.jsx')) return 'React JSX';
    if (filePath.includes('.sql')) return 'SQL';
    if (filePath.includes('.json')) return 'JSON';
    if (filePath.includes('.md')) return 'Markdown';
    if (filePath.includes('.yml') || filePath.includes('.yaml')) return 'YAML';
    if (filePath.includes('.toml')) return 'TOML';
    return 'File';
  };

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4 hover:shadow-sm transition-shadow">
      <div className="flex items-start">
        <div className="flex-shrink-0 mr-3">
          {getFileIcon(file)}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-gray-900 truncate">{file}</p>
            <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-800">
              {getFileType(file)}
            </span>
          </div>
          <p className="text-xs text-gray-500 mt-1">Key application file</p>
        </div>
      </div>
    </div>
  );
}

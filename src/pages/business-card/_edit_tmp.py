with open('D:/chainke-full/src/pages/business-card/BusinessCardPage.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

old = '          />\n        )\n\n        {step === \'review\' && (\n          <ReviewForm'
new = '''          />
        )}

        {step === 'upload' && activeTab === 'manual' && (
          <ManualForm
            onSubmit={handleManualSubmit}
            loading={loading}
            error={error}
          />
        )}

        {step === 'review' && (
          <ReviewForm'''

if old in content:
    content = content.replace(old, new, 1)
    with open('D:/chainke-full/src/pages/business-card/BusinessCardPage.tsx', 'w', encoding='utf-8') as f:
        f.write(content)
    print('SUCCESS: Added ManualForm rendering')
else:
    print('FAIL: Could not find anchor text')
    for i, line in enumerate(content.split('\n')):
        if 'ReviewForm' in line or '          />' in line:
            print(f'{i+1}: {repr(line)}')

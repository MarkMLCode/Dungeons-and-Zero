import re

def update_char_sheet_html_file(file_path, data):
    html_content = '''
<html>
<head>
<style>
    body {
        font-size: 13pt;
    }
    .title {
        font-size: 18pt;
        font-weight: bold;
    }
    .bold {
        font-weight: bold;
    }
</style>
</head>
<body>
'''

    for key, value in data.items():
        if value == '#title#':
            html_content += f'<p class="title">{key}</p>\n'
        elif key.startswith('#empty#'):
            # Output empty line
            html_content += '<br>\n'
        else:
            formatted_key = key.replace('#', '') # Remove '#' from key
            html_content += f'<span class="bold">{formatted_key}</span>: '
            value_str = str(value)
            link_pattern = re.compile(r'#LINK#\[(.*?)\]\((.*?)\)') # Process links
            last_end = 0
            processed_value = ''
            for match in link_pattern.finditer(value_str):
                # Text before the link
                if match.start() > last_end:
                    processed_value += value_str[last_end:match.start()]
                link_text = match.group(1)
                link_url = match.group(2)
                # Add the link
                processed_value += f'<a href="{link_url}">{link_text}</a>'
                last_end = match.end()
            # Remaining text after the last link
            if last_end < len(value_str):
                processed_value += value_str[last_end:]
                
            html_content += f'{processed_value}<br>\n'
    html_content += '</body></html>'

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
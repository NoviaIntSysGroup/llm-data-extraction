import json
import pandas as pd
import plotly.express as px

from dash import Dash, html, dcc, Output, Input

def visualize_results(results_path):
    with open(results_path, 'r', encoding='utf-8') as f:
        all_results = json.load(f)

    # Prepare the DataFrame with averages and associated data
    data = []

    for idx, result in enumerate(all_results):
        average = result['average']
        data.append({
            'Index': idx + 1,
            'Title': result['title'] if result.get('title') else f'Experiment {idx + 1}',
            'Average': average,
            'Prompt': result['prompt'],
            'Schema': result['schema']
        })

    df = pd.DataFrame(data)

    # Initialize the Dash app
    app = Dash(__name__)

    # Define the layout
    app.layout = html.Div([
        dcc.Graph(
            id='bar-chart',
            figure=px.bar(
                df,
                x="Index",
                y='Average',
                title='Average Results',
                labels={'Title': 'Title', 'Average': 'Average Similarity Score'}
            )
        ),
        html.Div(id='details', style={'marginTop': 20, 'backgroundColor': '#f0f0f0', 'padding': '10px'})
    ])

    # Callback to display prompt and schema when a bar is clicked
    @app.callback(
        Output('details', 'children'),
        Input('bar-chart', 'clickData')
    )
    def display_details(clickData):
        if clickData is None:
            return 'Click on a bar to see details.'
        else:
            index = clickData['points'][0]['x']
            prompt = df.loc[df['Index'] == index, 'Prompt'].values[0]
            schema = df.loc[df['Index'] == index, 'Schema'].values[0]
            return html.Div([
                html.H4('Prompt:'),
                html.Pre(prompt, style={'backgroundColor': '#f0f0f0', 'padding': '10px'}),
                html.H4('Schema:'),
                dcc.Markdown('```json\n' + schema + '\n```')
            ])

    # Run the app
    app.run_server(debug=True)

"""
Analytics routes
"""

from flask import render_template

def register_analytics_routes(app):
    """Register analytics routes with the Flask app"""
    
    @app.route('/analytics/path-analysis')
    def path_analysis_page():
        """Path Analysis page"""
        return render_template('Analysis/path_analysis.html')


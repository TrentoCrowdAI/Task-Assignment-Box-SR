import sqlalchemy
import pandas as pd


class Database:

    def __init__(self, user, password, db, host, port):
        self.user = user
        self.password = password
        self.db = db
        self.host = host
        self.port = port
        self.con, self.meta = self._connect()

    def _connect(self):
        '''Returns a connection and a metadata object'''
        # connect with the help of the PostgreSQL URL
        url = 'postgresql://{}:{}@{}:{}/{}'
        url = url.format(self.user, self.password, self.host, self.port, self.db)

        # connection object
        con = sqlalchemy.create_engine(url, client_encoding='utf8')

        # bind the connection to MetaData()
        meta = sqlalchemy.MetaData(bind=con, reflect=True)

        return con, meta

    def get_filters(self, job_id):
        '''
        :param job_id:
        :return: list of filter id
        '''

        sql_filter_list = '''
                                select c.* from job j 
                                join project p on j.project_id = p.id
                                join criterion c on c.project_id = p.id where j.id = {job_id};
                            '''.format(job_id=job_id)
        filter_array = pd.read_sql(sql_filter_list, self.con)['id'].values
        filter_list = [int(i) for i in filter_array]

        return filter_list

    def get_items_tolabel(self, filter_id, worker_id, job_id):
        '''
        :param filter_id:
        :param worker_id:
        :param job_id:
        :param max_votes:
        :return: list of ids of items to be labeled
        '''
        sql_job = '''
          select project_id, (data ->> 'votesPerTaskRule')::int as max_votes from job where id = {job_id}
        '''.format(job_id=job_id)
        max_votes, project_id = pd.read_sql(sql_job, self.con)[['max_votes', 'project_id']].values[0]

        sql_items_tolabel = '''
                              select i.id from item i
                                where i.project_id = {project_id}
                                and i.id not in (
                                  select t.item_id from task t
                                    where t.job_id = {job_id}
                                      and t.worker_id = {worker_id}
                                      and t.data @> '{{"criteria" : [{{"id": "{filter_id}"}}]}}'
                                      and (t.data ->> 'answered')::boolean = true
                                )
                                and compute_item_votes({job_id}::bigint, i.id, {filter_id}::bigint) < {max_votes};
                            '''.format(filter_id=filter_id, worker_id=worker_id, job_id=job_id, max_votes=max_votes, project_id=project_id)

        items_tolabel = pd.read_sql(sql_items_tolabel, self.con)['id'].values
        items_tolabel = [int(i) for i in items_tolabel]

        return items_tolabel

    def get_worker_votes_count(self, job_id, worker_id):
        '''
        :param worker_id:
        :param job_id:
        :return: the worker's votes count.
        '''
        sql_votes = '''
          select count(t.*) as count from task t
            where t.job_id = {job_id}
                and t.worker_id = {worker_id}
                and t.data ->> 'answered' = 'true'
        '''.format(job_id=job_id, worker_id=worker_id)
        votes_count = pd.read_sql(sql_votes, self.con)['count'].values[0]
        return votes_count

    def get_items_tolabel_msr(self, job_id):
        '''
        :param job_id:
        :return: items_votes_data
        '''
        # query for the project_id
        project_id = self.get_project_id(job_id)

        # query for getting unclassified items and their votes
        sql_items_votes = '''
            select i.id, 
                c.id as criteria_id, 
                compute_item_in_out_votes({job_id}, i.id, c.id, 'yes') as in_votes,
                compute_item_in_out_votes({job_id}, i.id, c.id, 'no') as out_votes
            from item i join criterion c on i.project_id = c.project_id
            where i.project_id = {project_id}
                and i.id not in (
                    select item_id from result where job_id = {job_id}
                );
            '''.format(job_id=job_id, project_id=project_id)
        items_votes_data = pd.read_sql(sql_items_votes, self.con)

        return items_votes_data

    def get_project_id(self, job_id):
        '''
        :param job_id:
        :return: project_id
        '''
        sql_project_id = "select project_id from job where id = {job_id};".format(job_id=job_id)
        project_id = pd.read_sql(sql_project_id, self.con)['project_id'].values[0]

        return project_id
    
    def get_job(self, job_id):
        '''
        :param job_id:
        :return: job
        '''
        sql_job = "select * from job where id = {job_id};".format(job_id=job_id)
        rows = pd.read_sql(sql_job, self.con).to_dict(orient='records')
        
        if rows:
          return rows[0]
        return None

    def get_update_filter_data(self, job_id, project_id):
        '''
        :param job_id:
        :param project_id:
        :return: item_filter_data
        '''
        # select all item-filter with at least one vote
        sql_item_filter_data = '''
                    select s.* from (select i.id, 
                        c.id as criteria_id, 
                        compute_item_in_out_votes({job_id}, i.id, c.id, 'yes') as in_votes,
                        compute_item_in_out_votes({job_id}, i.id, c.id, 'no') as out_votes
                    from item i join criterion c on i.project_id = c.project_id
                    where i.project_id = {project_id}
                    ) s
                    where (s.in_votes > 0 or s.out_votes > 0);
                    '''.format(job_id=job_id, project_id=project_id)
        item_filter_data = pd.read_sql(sql_item_filter_data, self.con)

        return item_filter_data
